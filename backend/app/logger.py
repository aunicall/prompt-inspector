"""Logging configuration module."""

import sys
import logging
from datetime import datetime
from pathlib import Path
from logging.handlers import RotatingFileHandler
from app.config import BASE_DIR

LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

_start_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
LOG_FILE = LOG_DIR / f"{_start_ts}.log"

LOG_FORMAT = "[%(asctime)s] [%(levelname)s] [%(name)s:%(lineno)d] %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging() -> logging.Logger:
    _logger = logging.getLogger("prompt_inspector")
    _logger.setLevel(logging.INFO)

    if _logger.hasHandlers():
        return _logger

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))

    file_handler = RotatingFileHandler(
        filename=LOG_FILE, mode="a",
        maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))

    _logger.addHandler(console_handler)
    _logger.addHandler(file_handler)
    return _logger


logger = setup_logging()
