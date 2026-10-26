from __future__ import annotations

import logging

import uvicorn

from .app import create_app
from .config import ConfigurationError, Settings
from .dependencies import inspect_dependencies
from .logging_setup import configure_logging


def main() -> None:
    configure_logging()
    try:
        settings = Settings.from_env()
        settings.validate_discord()
    except ConfigurationError as exc:
        logging.getLogger(__name__).error("Configuration error: %s", exc)
        raise SystemExit(2) from exc

    for issue in inspect_dependencies(settings).issues:
        logging.getLogger(__name__).error("Dependency check: %s", issue)

    logging.getLogger(__name__).info(
        "Player server starting at http://%s:%s. Screen capture remains stopped until /start.",
        settings.host,
        settings.port,
    )
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port, log_level="info")


if __name__ == "__main__":
    main()
