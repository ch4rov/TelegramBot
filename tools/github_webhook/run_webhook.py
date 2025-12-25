import os

import uvicorn

from tools.github_webhook.app import create_app


def main() -> None:
    host = (os.getenv("GITHUB_WEBHOOK_HOST") or "0.0.0.0").strip() or "0.0.0.0"
    port = int((os.getenv("GITHUB_WEBHOOK_PORT") or "8091").strip() or "8091")
    uvicorn.run(create_app(), host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
