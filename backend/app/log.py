"""Structured JSON logging (TRD Section 17)."""

import json
import logging

# Extra attrs the request middleware attaches; picked up here if present
_CONTEXT_FIELDS = ("method", "path", "status", "duration_ms", "client")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in _CONTEXT_FIELDS:
            if hasattr(record, field):
                entry[field] = getattr(record, field)
        if record.exc_info:
            entry["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(entry)


def setup_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)
    # Our middleware logs every request as JSON; uvicorn's plain access log duplicates it
    logging.getLogger("uvicorn.access").disabled = True
