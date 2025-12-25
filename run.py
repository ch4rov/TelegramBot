import os
import sys
import time
import subprocess
import threading
import shutil
import re
from pathlib import Path
import urllib.request

from dotenv import load_dotenv
from core.installs.ffmpeg_installer import check_and_install_ffmpeg


_URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com(?:/[^\s\"\']*)?", re.IGNORECASE)


def _is_true(raw: str | None) -> bool:
    return (raw or "").strip().lower() in ("1", "true", "yes", "y", "on")


def _is_test_env() -> bool:
    return _is_true(os.getenv("IS_TEST_ENV"))


def _cloudflared_path() -> str | None:
    configured = (os.getenv("CLOUDFLARED_BIN") or "").strip()
    if configured and os.path.exists(configured):
        return configured

    base = Path(__file__).resolve().parent
    local = base / "tools" / "cloudflared" / "cloudflared.exe"
    if local.exists():
        return str(local)

    return shutil.which("cloudflared")


def _download_cloudflared(dest: Path) -> bool:
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        return False

    url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "TelegramBot"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()
        tmp.write_bytes(data)
        tmp.replace(dest)
        return True
    except Exception:
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass
        return False


def _ensure_cloudflared() -> str | None:
    existing = _cloudflared_path()
    if existing:
        return existing

    if not _is_true(os.getenv("TEST_AUTO_DOWNLOAD_CLOUDFLARED")):
        return None

    base = Path(__file__).resolve().parent
    dest = base / "tools" / "cloudflared" / "cloudflared.exe"
    print("[TEST-TUNNEL] Downloading cloudflared...")
    ok = _download_cloudflared(dest)
    if ok and dest.exists():
        return str(dest)
    print("[TEST-TUNNEL] Failed to download cloudflared.")
    return None


def _replace_env_line(text: str, key: str, value: str) -> str:
    lines = text.splitlines(True)
    out = []
    found = False
    prefix = key + "="
    for line in lines:
        if line.startswith(prefix):
            out.append(prefix + value + "\n")
            found = True
        else:
            out.append(line)
    if not found:
        if out and not out[-1].endswith("\n"):
            out[-1] = out[-1] + "\n"
        out.append(prefix + value + "\n")
    return "".join(out)


def _maybe_write_env(url: str) -> None:
    if not _is_true(os.getenv("TEST_QUICK_TUNNEL_WRITE_ENV")):
        return
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        return
    try:
        raw = env_path.read_text(encoding="utf-8")
    except Exception:
        return
    raw = _replace_env_line(raw, "TEST_PUBLIC_BASE_URL", url)
    raw = _replace_env_line(raw, "TEST_MINIAPP_PUBLIC_URL", url)
    try:
        env_path.write_text(raw, encoding="utf-8")
    except Exception:
        return


def _start_miniapp_backend(child_env: dict) -> subprocess.Popen | None:
    if not _is_true(os.getenv("TEST_AUTO_START_MINIAPP_BACKEND")):
        return None
    host = (os.getenv("MINIAPP_BACKEND_HOST") or "0.0.0.0").strip() or "0.0.0.0"
    port = (os.getenv("MINIAPP_BACKEND_PORT") or "8090").strip() or "8090"
    child_env = dict(child_env)
    child_env["MINIAPP_BACKEND_HOST"] = host
    child_env["MINIAPP_BACKEND_PORT"] = port
    try:
        return subprocess.Popen([sys.executable, "-m", "miniapp_backend.run_miniapp"], env=child_env)
    except Exception:
        return None


def _start_quick_tunnel(child_env: dict) -> tuple[subprocess.Popen | None, str]:
    exe = _cloudflared_path() or _ensure_cloudflared()
    if not exe:
        return None, ""

    origin = (os.getenv("TEST_QUICK_TUNNEL_ORIGIN_URL") or "http://127.0.0.1:8090").strip() or "http://127.0.0.1:8090"
    log_path = str((Path(__file__).resolve().parent / "tempfiles" / "cloudflared_test.log"))
    try:
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        Path(log_path).touch(exist_ok=True)
    except Exception:
        pass

    args = [exe, "tunnel", "--no-autoupdate", "--url", origin]

    try:
        proc = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=child_env,
        )
    except Exception:
        return None, ""

    url_box = {"url": ""}

    def _pump():
        try:
            with open(log_path, "a", encoding="utf-8", errors="ignore") as f:
                while True:
                    if proc.stdout is None:
                        break
                    line = proc.stdout.readline()
                    if not line:
                        break
                    f.write(line)
                    f.flush()
                    if not url_box["url"]:
                        m = _URL_RE.search(line)
                        if m:
                            url_box["url"] = m.group(0).rstrip("/\r\n\t \"\'")
        except Exception:
            return

    t = threading.Thread(target=_pump, daemon=True)
    t.start()

    deadline = time.time() + float(os.getenv("TEST_QUICK_TUNNEL_TIMEOUT_SEC") or "20")
    while time.time() < deadline:
        if url_box["url"]:
            break
        if proc.poll() is not None:
            break
        time.sleep(0.2)

    return proc, url_box["url"]

def main():
    check_and_install_ffmpeg()

    base_dir = Path(__file__).resolve().parent
    env_path = base_dir / ".env"
    if env_path.exists():
        try:
            load_dotenv(dotenv_path=env_path)
        except Exception:
            pass

    tunnel_proc: subprocess.Popen | None = None
    miniapp_proc: subprocess.Popen | None = None

    while True:
        child_env = os.environ.copy()

        if _is_test_env() and not _is_true(os.getenv("TEST_AUTO_QUICK_TUNNEL_DISABLED")):
            try:
                if tunnel_proc and tunnel_proc.poll() is None:
                    tunnel_proc.terminate()
            except Exception:
                pass
            tunnel_proc = None

            try:
                if miniapp_proc and miniapp_proc.poll() is None:
                    miniapp_proc.terminate()
            except Exception:
                pass
            miniapp_proc = None

            miniapp_proc = _start_miniapp_backend(child_env)
            tunnel_proc, url = _start_quick_tunnel(child_env)

            origin = (os.getenv("TEST_QUICK_TUNNEL_ORIGIN_URL") or "http://127.0.0.1:8090").strip() or "http://127.0.0.1:8090"

            if url:
                child_env["TEST_PUBLIC_BASE_URL"] = url
                child_env["TEST_MINIAPP_PUBLIC_URL"] = url
                _maybe_write_env(url)
                print("\n[TEST-TUNNEL] Origin (local): " + origin)
                print("[TEST-TUNNEL] Public (HTTPS): " + url)
                print("[TEST-TUNNEL] Paste into Telegram settings (no port needed):")
                print("[TEST-TUNNEL] TEST_PUBLIC_BASE_URL=" + url)
                print("[TEST-TUNNEL] TEST_MINIAPP_PUBLIC_URL=" + url)
            else:
                exe = _cloudflared_path()
                if not exe:
                    print("\n[TEST-TUNNEL] cloudflared not found.")
                    print("[TEST-TUNNEL] Put it at tools\\cloudflared\\cloudflared.exe or set CLOUDFLARED_BIN.")
                else:
                    print("\n[TEST-TUNNEL] cloudflared started but URL was not detected.")
                    print("[TEST-TUNNEL] See tempfiles\\cloudflared_test.log")

        print("\n[RUNNER] Starting main.py...")
        process = subprocess.Popen([sys.executable, "main.py"], env=child_env)
        
        try:
            process.wait()
        except KeyboardInterrupt:
            print("\n[RUNNER] Stopping bot...")
            process.terminate()

            try:
                if tunnel_proc and tunnel_proc.poll() is None:
                    tunnel_proc.terminate()
            except Exception:
                pass

            try:
                if miniapp_proc and miniapp_proc.poll() is None:
                    miniapp_proc.terminate()
            except Exception:
                pass
            
            try:
                subprocess.run("taskkill /F /T /PID " + str(process.pid), shell=True, stderr=subprocess.DEVNULL)
            except: pass
            
            break

        exit_code = process.returncode
        print("[RUNNER] Bot crashed (code " + str(exit_code) + "). Restarting in 5 sec...")
        time.sleep(5)

if __name__ == "__main__":
    main()