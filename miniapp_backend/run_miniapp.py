import os

import uvicorn

from miniapp_backend.app.api import create_app


def main() -> None:
    host = (os.getenv("MINIAPP_BACKEND_HOST") or "0.0.0.0").strip() or "0.0.0.0"
    port_raw = (os.getenv("MINIAPP_BACKEND_PORT") or "8090").strip() or "8090"
    try:
        port = int(port_raw)
    except Exception:
        port = 8090

    uvicorn.run(create_app(), host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
