"""
Logging configuration for the FastAPI application.
"""

import logging
import os
import sys
from datetime import datetime
from typing import Optional


class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    FAINT = "\033[2m"
    DEBUG = "\033[36m"
    INFO = "\033[32m"
    WARNING = "\033[33m"
    ERROR = "\033[31m"
    CRITICAL = "\033[35m"
    TIMESTAMP = "\033[90m"
    LOGGER_NAME = "\033[36m"


class ColoredFormatter(logging.Formatter):
    LEVEL_COLORS = {
        logging.DEBUG: Colors.DEBUG,
        logging.INFO: Colors.INFO,
        logging.WARNING: Colors.WARNING,
        logging.ERROR: Colors.ERROR,
        logging.CRITICAL: Colors.CRITICAL,
    }

    def format(self, record: logging.LogRecord) -> str:
        level_color = self.LEVEL_COLORS.get(record.levelno, Colors.RESET)
        timestamp = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
        level_name = f"{record.levelname:>5}"
        logger_name = record.name[-40:] if len(record.name) > 40 else record.name

        formatted = (
            f"{Colors.FAINT}{timestamp}{Colors.RESET} "
            f"{level_color}{level_name}{Colors.RESET} "
            f"{Colors.FAINT}---{Colors.RESET} "
            f"{Colors.FAINT}[{Colors.RESET}"
            f"{Colors.LOGGER_NAME}{logger_name:>40}{Colors.RESET}"
            f"{Colors.FAINT}]{Colors.RESET} "
            f"{Colors.FAINT}:{Colors.RESET} "
            f"{record.getMessage()}"
        )
        if record.exc_info:
            formatted += "\n" + self.formatException(record.exc_info)
        return formatted


class PlainFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S")
        level_name = f"{record.levelname:>5}"
        logger_name = record.name[-40:] if len(record.name) > 40 else record.name
        formatted = f"{timestamp} {level_name} --- [{logger_name:>40}] : {record.getMessage()}"
        if record.exc_info:
            formatted += "\n" + self.formatException(record.exc_info)
        return formatted


def setup_logger(name: str = "foodies", level: Optional[str] = None, log_file: Optional[str] = None) -> logging.Logger:
    log_level_str = level or os.getenv("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)

    logger = logging.getLogger(name)
    logger.setLevel(log_level)
    logger.handlers.clear()

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(ColoredFormatter())
    logger.addHandler(console_handler)

    file_path = log_file or os.getenv("LOG_FILE")
    if file_path:
        file_handler = logging.FileHandler(file_path)
        file_handler.setLevel(log_level)
        file_handler.setFormatter(PlainFormatter())
        logger.addHandler(file_handler)

    logger.propagate = False
    return logger


logger = setup_logger()
