import logging
from pathlib import Path

from ph.logging_config import configure_logging


def test_logging_can_be_disabled_without_writing_to_the_terminal() -> None:
    logger = configure_logging(None, "DEBUG")

    assert logger.level == logging.DEBUG
    assert len(logger.handlers) == 1
    assert isinstance(logger.handlers[0], logging.NullHandler)


def test_logging_writes_structured_records_to_the_requested_file(tmp_path: Path) -> None:
    log_file = tmp_path / "logs" / "pocket-harbor.log"
    logger = configure_logging(log_file, "not-a-level")

    logger.info("download completed")
    for handler in logger.handlers:
        handler.flush()

    content = log_file.read_text(encoding="utf-8")
    assert "INFO ph: download completed" in content
    assert logger.level == logging.INFO


def test_logging_failure_falls_back_without_crashing(tmp_path: Path) -> None:
    parent_file = tmp_path / "not-a-directory"
    parent_file.write_text("occupied", encoding="utf-8")

    logger = configure_logging(parent_file / "application.log")

    assert isinstance(logger.handlers[0], logging.NullHandler)
