"""
Structured logging utilities for ASO services.
"""

import os
import sys
import json
import logging
from datetime import datetime
from typing import Optional


class JSONFormatter(logging.Formatter):
    """JSON log formatter for structured logging."""

    def __init__(self, service_name: str):
        super().__init__()
        self.service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "time": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "msg": record.getMessage(),
            "service": self.service_name,
            "logger": record.name,
        }

        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        # Add extra fields
        for key, value in record.__dict__.items():
            if key not in (
                "name", "msg", "args", "levelname", "levelno", "pathname",
                "filename", "module", "exc_info", "exc_text", "stack_info",
                "lineno", "funcName", "created", "msecs", "relativeCreated",
                "thread", "threadName", "processName", "process", "message",
            ):
                log_entry[key] = value

        return json.dumps(log_entry)


def setup_logging(
    service_name: str,
    level: str = "INFO",
    json_format: bool = True,
) -> logging.Logger:
    """
    Set up structured logging for a service.

    Args:
        service_name: Name of the service for log entries
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_format: Use JSON format (default) or plain text

    Returns:
        Configured logger
    """
    log_level = os.environ.get("LOG_LEVEL", level).upper()

    # Get root logger
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, log_level, logging.INFO))

    # Remove existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    # Create console handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(getattr(logging, log_level, logging.INFO))

    if json_format:
        handler.setFormatter(JSONFormatter(service_name))
    else:
        handler.setFormatter(logging.Formatter(
            f"%(asctime)s [{service_name}] %(levelname)s %(name)s: %(message)s"
        ))

    logger.addHandler(handler)
    return logger


def get_logger(name: str) -> logging.Logger:
    """Get a named logger."""
    return logging.getLogger(name)
