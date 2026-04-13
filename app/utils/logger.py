from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Mapping


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        extra = getattr(record, "extra_fields", None)
        if isinstance(extra, Mapping):
            for key, value in extra.items():
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


class StructuredLogger:
    def __init__(self, name: str) -> None:
        self._logger = logging.getLogger(name)

    def _log(self, level: int, message: str, **fields: Any) -> None:
        self._logger.log(level, message, extra={"extra_fields": fields})

    def debug(self, message: str, **fields: Any) -> None:
        self._log(logging.DEBUG, message, **fields)

    def info(self, message: str, **fields: Any) -> None:
        self._log(logging.INFO, message, **fields)

    def warning(self, message: str, **fields: Any) -> None:
        self._log(logging.WARNING, message, **fields)

    def error(self, message: str, **fields: Any) -> None:
        self._log(logging.ERROR, message, **fields)

    def exception(self, message: str, **fields: Any) -> None:
        self._logger.error(message, exc_info=True, extra={"extra_fields": fields})


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    if getattr(root, "_ragfier_configured", False):
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.handlers = [handler]
    root.setLevel(level.upper())
    root._ragfier_configured = True  # type: ignore[attr-defined]


def get_logger(name: str) -> StructuredLogger:
    configure_logging()
    return StructuredLogger(name)
