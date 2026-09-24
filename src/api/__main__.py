"""Launch the FastAPI sidecar: ``python -m src.api``.

Reads the bind host/port from Config (API_HOST / API_PORT) so the Electron main
process and the sidecar agree on where to talk.
"""

import uvicorn

from ..config import Config, ConfigError


def main() -> None:
    try:
        config = Config.load_and_validate()
        host, port = config.api_host, config.api_port
    except ConfigError:
        # Fall back to defaults; the /api/session call will surface the real
        # config error to the UI with an actionable message.
        host, port = "127.0.0.1", 8765

    uvicorn.run("src.api.server:app", host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
