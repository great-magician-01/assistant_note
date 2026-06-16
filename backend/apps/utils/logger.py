"""Logging module using Python standard library.

File rotation strategy:
  - One directory per day: {LOG_DIR}/{YYYY-MM-DD}/
  - Files within a day: log1.log, log2.log, log3.log, ...
  - A new file is created when the current file exceeds 200 MB
  - A new directory is created when the date changes

Thread-safe: all file operations are protected by a threading.Lock.

Trace ID:
  Each HTTP request is assigned a unique trace_id via FastAPI middleware.
  The trace_id is stored in a contextvars.ContextVar and injected into
  every log record via a logging Filter, so all logs from the same
  request can be correlated.
"""

import logging
import os
import threading
import uuid
from contextvars import ContextVar
from datetime import date
from pathlib import Path

from backend.apps.utils.config import settings

# 200 MB per file
_MAX_BYTES = 200 * 1024 * 1024

_LOG_FORMAT = "%(asctime)s.%(msecs)03d | %(levelname)-8s | [%(trace_id)s] | %(name)s | %(filename)s:%(lineno)d | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# ── Trace ID ─────────────────────────────────────────────────────────────────

# ContextVar is coroutine-safe: each asyncio Task gets its own copy,
# so concurrent requests never interfere with each other.
_trace_id_var: ContextVar[str] = ContextVar("trace_id", default="-")


def get_trace_id() -> str:
    """Get the current trace_id from context."""
    return _trace_id_var.get()


def set_trace_id(trace_id: str) -> None:
    """Set the trace_id for the current context."""
    _trace_id_var.set(trace_id)


def new_trace_id() -> str:
    """Generate a new trace_id and set it in the current context."""
    tid = uuid.uuid4().hex[:16]
    _trace_id_var.set(tid)
    return tid


class _TraceIdFilter(logging.Filter):
    """Inject the current trace_id into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = _trace_id_var.get()  # type: ignore[attr-defined]
        return True


# ── Rotating file handler ────────────────────────────────────────────────────


class _DateSizeRotatingFileHandler(logging.Handler):
    """Logging handler that rotates by date AND file size.

    Directory structure::

        {LOG_DIR}/2026-06-17/log1.log
        {LOG_DIR}/2026-06-17/log2.log   ← created when log1.log > 200 MB
        {LOG_DIR}/2026-06-18/log1.log   ← created when date changes
    """

    def __init__(self, log_dir: str, max_bytes: int = _MAX_BYTES, encoding: str = "utf-8") -> None:
        super().__init__()
        self.log_dir = log_dir
        self.max_bytes = max_bytes
        self.encoding = encoding
        self._current_date: date = date.today()
        self._file_index: int = 1
        self._file = None
        self._lock = threading.Lock()

        # Ensure base dir exists
        os.makedirs(log_dir, exist_ok=True)

        # Resume from latest existing log for today
        day_dir = self._day_dir()
        self._file_index = self._find_next_index(day_dir)

        # Open initial file
        self._open_file()

    # ── Core handler method ────────────────────────────────────────────────

    def emit(self, record: logging.LogRecord) -> None:
        """Write a log record. Thread-safe via lock."""
        with self._lock:
            try:
                self._maybe_rollover()
                msg = self.format(record) + "\n"
                self._file.write(msg)
                self._file.flush()
            except Exception:
                self.handleError(record)

    # ── File management ────────────────────────────────────────────────────

    def _day_dir(self) -> Path:
        return Path(self.log_dir) / self._current_date.strftime("%Y-%m-%d")

    def _current_filepath(self) -> Path:
        day_dir = self._day_dir()
        day_dir.mkdir(parents=True, exist_ok=True)
        return day_dir / f"log{self._file_index}.log"

    def _find_next_index(self, day_dir: Path) -> int:
        """Return the index to use: reuse the latest file if under size limit,
        otherwise increment."""
        if not day_dir.is_dir():
            return 1

        indices: list[int] = []
        for name in os.listdir(day_dir):
            if name.startswith("log") and name.endswith(".log"):
                try:
                    idx = int(name[3:-4])
                    indices.append(idx)
                except ValueError:
                    pass

        if not indices:
            return 1

        max_idx = max(indices)
        filepath = day_dir / f"log{max_idx}.log"
        try:
            if filepath.stat().st_size < self.max_bytes:
                return max_idx
        except OSError:
            pass

        return max_idx + 1

    def _maybe_rollover(self) -> None:
        """Check if rotation is needed and perform it."""
        today = date.today()

        # Date changed → new directory, reset index
        if today != self._current_date:
            self._close_file()
            self._current_date = today
            self._file_index = 1
            self._open_file()
            return

        # Size exceeded → same directory, increment index
        try:
            if self._current_filepath().stat().st_size >= self.max_bytes:
                self._close_file()
                self._file_index += 1
                self._open_file()
        except OSError:
            pass

    def _open_file(self) -> None:
        filepath = self._current_filepath()
        self._file = open(filepath, "a", encoding=self.encoding)

    def _close_file(self) -> None:
        if self._file and not self._file.closed:
            self._file.close()

    def close(self) -> None:
        """Close the handler and its file."""
        with self._lock:
            self._close_file()
        super().close()


# ── Setup ────────────────────────────────────────────────────────────────────

def setup_logging() -> None:
    """Configure the root logger with console + rotating file handlers."""
    root = logging.getLogger()

    # Avoid duplicate handlers if called multiple times
    if root.handlers:
        return

    level = logging.DEBUG if settings.DEBUG else logging.INFO
    root.setLevel(level)

    # Trace ID filter — injects trace_id into every record
    trace_filter = _TraceIdFilter()
    root.addFilter(trace_filter)

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    # Console handler
    console = logging.StreamHandler()
    console.setLevel(level)
    console.setFormatter(formatter)
    console.addFilter(trace_filter)
    root.addHandler(console)

    # File handler (date + size rotating)
    file_handler = _DateSizeRotatingFileHandler(
        log_dir=settings.LOG_DIR,
        max_bytes=_MAX_BYTES,
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    file_handler.addFilter(trace_filter)
    root.addHandler(file_handler)

    # Quiet down noisy third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.INFO if settings.DEBUG else logging.WARNING
    )

    logging.info("Logging initialized: level=%s, dir=%s", logging.getLevelName(level), settings.LOG_DIR)
