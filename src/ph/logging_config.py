"""Application logging that stays out of the curses terminal."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOGGER_NAME = "ph"
DEFAULT_LOG_LEVEL = "INFO"
MAX_LOG_BYTES = 1024 * 1024
LOG_BACKUP_COUNT = 2


def configure_logging(log_file: Path | None, level_name: str = DEFAULT_LOG_LEVEL) -> logging.Logger:
    """Configure one package logger, writing only to a file when one is requested."""

    logger = logging.getLogger(LOGGER_NAME)
    for existing_handler in logger.handlers:
        existing_handler.close()
    logger.handlers.clear()
    logger.propagate = False
    level = getattr(logging, level_name.upper(), logging.INFO)
    logger.setLevel(level)

    if log_file is None:
        logger.addHandler(logging.NullHandler())
        return logger

    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handler: logging.Handler = RotatingFileHandler(
            log_file,
            maxBytes=MAX_LOG_BYTES,
            backupCount=LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
    except OSError:
        handler = logging.NullHandler()
    handler.setLevel(level)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s: %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    )
    logger.addHandler(handler)
    return logger
