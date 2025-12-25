import asyncio
import hmac
import hashlib
import json
import os
import subprocess
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request


def _b(v: str | None) -> bytes:
    return (v or "").encode("utf-8")


def _clean(raw: str | None) -> str:
    return (raw or "").strip().strip('"').strip("'").strip()


def _timing_safe_eq(a: str, b: str) -> bool:
    try:
        return hmac.compare_digest(a, b)
    except Exception:
        return False


def _verify_github_signature(secret: str, body: bytes, signature_header: str | None) -> None:
    if not secret:
        raise HTTPException(status_code=500, detail="missing_secret")

    sig = (signature_header or "").strip()
    if not sig.startswith("sha256="):
        raise HTTPException(status_code=401, detail="bad_signature")

    recv = sig.split("=", 1)[1].strip().lower()
    mac = hmac.new(_b(secret), body, hashlib.sha256).hexdigest().lower()

    if not _timing_safe_eq(mac, recv):
        raise HTTPException(status_code=401, detail="bad_signature")


def _run(cmd: list[str], cwd: str) -> tuple[int, str]:
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    out = (p.stdout or "") + ("\n" if p.stdout and p.stderr else "") + (p.stderr or "")
    return int(p.returncode), out.strip()


def _update_repo_and_restart(repo_dir: str, branch: str, services: str, hard_reset: bool) -> dict[str, Any]:
    env = os.environ.copy()

    _run(["git", "config", "--global", "--add", "safe.directory", repo_dir], cwd=repo_dir)

    code, out = _run(["git", "fetch", "origin", branch, "--prune"], cwd=repo_dir)
    if code != 0:
        return {"ok": False, "step": "git_fetch", "code": code, "output": out}

    code, out = _run(["git", "pull", "--ff-only", "origin", branch], cwd=repo_dir)
    if code != 0:
        if hard_reset:
            code2, out2 = _run(["git", "reset", "--hard", f"origin/{branch}"], cwd=repo_dir)
            if code2 != 0:
                return {"ok": False, "step": "git_reset", "code": code2, "output": out2}
        else:
            return {"ok": False, "step": "git_pull", "code": code, "output": out}

    compose_cmd = ["docker", "compose", "up", "-d", "--build"] + services.split()
    p = subprocess.run(compose_cmd, cwd=repo_dir, env=env, capture_output=True, text=True)
    out = (p.stdout or "") + ("\n" if p.stdout and p.stderr else "") + (p.stderr or "")

    return {"ok": p.returncode == 0, "step": "compose_up", "code": int(p.returncode), "output": out.strip()}


def create_app() -> FastAPI:
    app = FastAPI()

    secret = _clean(os.getenv("GITHUB_WEBHOOK_SECRET"))
    branch = _clean(os.getenv("GITHUB_WEBHOOK_BRANCH")) or "main"
    services = _clean(os.getenv("GITHUB_WEBHOOK_SERVICES")) or "telegrambot miniapp-backend"
    repo_dir = _clean(os.getenv("GITHUB_WEBHOOK_REPO_DIR")) or "/repo"
    hard_reset = _clean(os.getenv("GITHUB_WEBHOOK_HARD_RESET")).lower() in ("1", "true", "yes")

    lock = asyncio.Lock()

    @app.get("/health")
    async def health():
        return {"ok": True}

    @app.post("/webhook/github")
    async def github_webhook(
        request: Request,
        x_hub_signature_256: str | None = Header(default=None, alias="X-Hub-Signature-256"),
        x_github_event: str | None = Header(default=None, alias="X-GitHub-Event"),
    ):
        body = await request.body()
        _verify_github_signature(secret, body, x_hub_signature_256)

        event = (x_github_event or "").strip().lower()
        if event not in ("push", "ping"):
            return {"ok": True, "ignored": True, "event": event}

        if event == "ping":
            return {"ok": True, "pong": True}

        try:
            payload = json.loads(body.decode("utf-8")) if body else {}
        except Exception:
            payload = {}

        ref = (payload.get("ref") or "").strip()
        want_ref = f"refs/heads/{branch}"
        if ref and ref != want_ref:
            return {"ok": True, "ignored": True, "reason": "wrong_branch", "ref": ref, "want": want_ref}

        if lock.locked():
            raise HTTPException(status_code=409, detail="update_in_progress")

        async with lock:
            result = await asyncio.to_thread(_update_repo_and_restart, repo_dir, branch, services, hard_reset)
            if not result.get("ok"):
                raise HTTPException(status_code=500, detail=result)
            return result

    return app
