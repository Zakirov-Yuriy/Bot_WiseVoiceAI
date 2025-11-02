"""
Structured JSON logging configuration for ELK stack compatibility.
"""

import json
import logging
import sys
from datetime import datetime
from typing import Dict, Any, Optional
import traceback


class JSONFormatter(logging.Formatter):
    """
    Custom JSON formatter for structured logging compatible with ELK stack.
    """

    def __init__(self, include_extra: bool = True):
        super().__init__()
        self.include_extra = include_extra

    def format(self, record: logging.LogRecord) -> str:
        """
        Format log record as JSON.

        Args:
            record: Log record to format

        Returns:
            JSON formatted log entry
        """
        # Base log entry structure
        log_entry = {
            "@timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "process": record.process,
            "thread": record.thread,
            "thread_name": record.threadName,
        }

        # Add exception information if present
        if record.exc_info:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else "Unknown",
                "message": str(record.exc_info[1]) if record.exc_info[1] else "",
                "traceback": traceback.format_exception(*record.exc_info)
            }

        # Add extra fields if enabled
        if self.include_extra and hasattr(record, '__dict__'):
            extra_fields = {}
            for key, value in record.__dict__.items():
                # Skip standard logging fields
                if key not in {
                    'name', 'msg', 'args', 'levelname', 'levelno', 'pathname',
                    'filename', 'module', 'exc_info', 'exc_text', 'stack_info',
                    'lineno', 'funcName', 'created', 'msecs', 'relativeCreated',
                    'thread', 'threadName', 'processName', 'process', 'message'
                }:
                    # Convert non-serializable objects to strings
                    try:
                        json.dumps(value)
                        extra_fields[key] = value
                    except (TypeError, ValueError):
                        extra_fields[key] = str(value)

            if extra_fields:
                log_entry["extra"] = extra_fields

        # Add context fields for bot-specific information
        if hasattr(record, 'user_id'):
            log_entry["user_id"] = record.user_id
        if hasattr(record, 'request_id'):
            log_entry["request_id"] = record.request_id
        if hasattr(record, 'correlation_id'):
            log_entry["correlation_id"] = record.correlation_id
        if hasattr(record, 'component'):
            log_entry["component"] = record.component
        if hasattr(record, 'operation'):
            log_entry["operation"] = record.operation
        if hasattr(record, 'duration'):
            log_entry["duration"] = record.duration

        return json.dumps(log_entry, ensure_ascii=False)


class BotAdapter(logging.LoggerAdapter):
    """
    Logger adapter that adds bot-specific context to log records.
    """

    def __init__(self, logger: logging.Logger, extra: Optional[Dict[str, Any]] = None):
        super().__init__(logger, extra or {})

    def process(self, msg: str, kwargs: Dict[str, Any]) -> tuple:
        """
        Process log record to add context.

        Args:
            msg: Log message
            kwargs: Keyword arguments

        Returns:
            Tuple of (message, kwargs)
        """
        # Add context from adapter's extra
        if 'extra' not in kwargs:
            kwargs['extra'] = {}

        kwargs['extra'].update(self.extra)

        # Add stack info for better debugging
        if self.logger.isEnabledFor(logging.DEBUG):
            kwargs['stack_info'] = True

        return msg, kwargs


def setup_logging(
    level: Optional[str] = None,
    json_format: Optional[bool] = None,
    log_file: Optional[str] = None,
    component: Optional[str] = None
) -> logging.Logger:
    """
    Set up structured logging for the application.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_format: Whether to use JSON formatting
        log_file: Optional log file path
        component: Component name for log entries

    Returns:
        Configured logger instance
    """
    # Clear existing handlers
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Set log level
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    root_logger.setLevel(numeric_level)

    # Create formatter
    if json_format:
        formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler (optional)
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(numeric_level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    # Create main logger with component context
    logger = logging.getLogger(component)
    logger.setLevel(numeric_level)

    # Create adapter with component context
    adapter = BotAdapter(logger, {"component": component})

    return adapter


def get_logger(name: str, **context) -> BotAdapter:
    """
    Get a logger with additional context.

    Args:
        name: Logger name
        **context: Additional context fields

    Returns:
        Logger adapter with context
    """
    logger = logging.getLogger(name)
    return BotAdapter(logger, context)


# Global logger instance - will be initialized with settings later
logger = None
