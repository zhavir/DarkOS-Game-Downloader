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

    return configure_logging_with_fallback(log_file, level_name)


def configure_logging_with_fallback(
    log_file: Path | None,
    level_name: str = DEFAULT_LOG_LEVEL,
    fallback_file: Path | None = None,
) -> logging.Logger:
    """Configure logging and use a writable fallback when the preferred path fails."""

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

    handler: logging.Handler | None = None
    failures: list[tuple[Path, OSError]] = []
    candidates = tuple(
        dict.fromkeys(path for path in (log_file, fallback_file) if path is not None)
    )
    for candidate in candidates:
        try:
            candidate.parent.mkdir(parents=True, exist_ok=True)
            handler = RotatingFileHandler(
                candidate,
                maxBytes=MAX_LOG_BYTES,
                backupCount=LOG_BACKUP_COUNT,
                encoding="utf-8",
            )
        except OSError as error:
            failures.append((candidate, error))
            continue
        break
    if handler is None:
        handler = logging.NullHandler()
    handler.setLevel(level)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s: %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    )
    logger.addHandler(handler)
    active_file = active_log_file(logger)
    if active_file is not None:
        if failures:
            failed_path, error = failures[0]
            logger.warning(
                "Could not open requested log path=%s error=%s; using fallback=%s",
                failed_path,
                error,
                active_file,
            )
        logger.info(
            "File logging active path=%s level=%s", active_file, logging.getLevelName(level)
        )
    return logger


def active_log_file(logger: logging.Logger | None = None) -> Path | None:
    """Return the absolute path used by the package file handler, if enabled."""

    selected = logger or logging.getLogger(LOGGER_NAME)
    for handler in selected.handlers:
        if isinstance(handler, logging.FileHandler):
            return Path(handler.baseFilename)
    return None
