import hashlib
import hmac
import json
from urllib.parse import parse_qsl


class InitDataError(Exception):
    pass


def _check_string(bot_token: str) -> bytes:
    return hashlib.sha256(bot_token.encode("utf-8")).digest()


def validate_init_data(init_data: str, bot_token: str) -> dict:
    if not init_data or not bot_token:
        raise InitDataError("missing")

    pairs = parse_qsl(init_data, keep_blank_values=True, strict_parsing=False)
    data = {k: v for k, v in pairs}
    recv_hash = data.pop("hash", None)
    if not recv_hash:
        raise InitDataError("no_hash")
    try:
        recv_hash = str(recv_hash).lower()
    except Exception:
        pass

    sorted_items = sorted(data.items(), key=lambda kv: kv[0])
    payload = "\n".join([f"{k}={v}" for k, v in sorted_items])

    secret = _check_string(bot_token)
    calc = hmac.new(secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(calc, recv_hash):
        raise InitDataError("bad_hash")

    return data


def user_id_from_init_data(data: dict) -> int | None:
    raw = data.get("user")
    if not raw:
        return None
    try:
        obj = json.loads(raw)
    except Exception:
        return None
    uid = obj.get("id") if isinstance(obj, dict) else None
    try:
        return int(uid)
    except Exception:
        return None


def validate_init_data_admin(init_data: str, bot_token: str, admin_ids: list[int]) -> dict:
    data = validate_init_data(init_data, bot_token)
    uid = user_id_from_init_data(data)
    if uid is None or int(uid) not in set(int(x) for x in (admin_ids or [])):
        raise InitDataError("forbidden")
    return data
