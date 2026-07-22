# ~/src/services/logging.py
# Centralized logging configuration for console + rotating file logs.

import queue
import threading
import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Any

from config.loader import OPERATING_MODE, PROJECT_ROOT

PRINT_PREFIX = "LOG MANAGER"
LOG_NAME = "db_service_logs"

DEBUG_ENABLED = OPERATING_MODE == "development"

_LOG_DIR = PROJECT_ROOT / "logs"
_LOG_DIR.mkdir(parents=True, exist_ok=True)

_log_queue = queue.Queue(maxsize=10000)  # Limit the queue size to prevent excessive memory usage
_worker_started = False

_warned_incase_logging_not_started = False  # Flag to ensure we only warn once if logging is not started

def _build_logger() -> logging.Logger:
    logger = logging.getLogger("database_service")
    logger.setLevel(logging.DEBUG if DEBUG_ENABLED else logging.INFO)
    logger.propagate = False

    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG if DEBUG_ENABLED else logging.INFO)
    console_handler.setFormatter(formatter)

    file_handler = TimedRotatingFileHandler(
        filename=str(_LOG_DIR / f"{LOG_NAME}.log"),
        when="midnight",
        interval=1,
        backupCount=7,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG if DEBUG_ENABLED else logging.INFO)
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    return logger


def initialize_logging() -> None:
    """Starts a worker thread that processes log messages from a queue."""
    global _worker_started
    if not _worker_started:
        _worker_started = True
        worker_thread = threading.Thread(target=_log_message_worker, daemon=True, name="LogMessageWorker")
        worker_thread.start()

def log_message(*args: Any, **kwargs: Any) -> None:
    """Log a message with print-like call style."""
    message = " ".join(str(arg) for arg in args)
    
    if not _worker_started:
        global _warned_incase_logging_not_started
        if not _warned_incase_logging_not_started:
            print(f"[WARNING] [{PRINT_PREFIX}] Logging worker not started. Messages will be printed directly:")
            _warned_incase_logging_not_started = True
        print(message)
        return

    if not message:
        return
    
    try:
        _log_queue.put_nowait(message)
    except queue.Full:
        pass

def _log_message_worker():
    logger = _build_logger()

    while True:
        try:
            message = _log_queue.get()
            if message.startswith("[ERROR]"):
                logger.error(message)
            elif message.startswith("[WARNING]"):
                logger.warning(message)
            elif message.startswith("[DEBUG]"):
                logger.debug(message)
            elif message.startswith("[CRITICAL]"):
                logger.critical(message)
            else:
                logger.info(message)
        except Exception as e:
            print(f"[CRITICAL] [{PRINT_PREFIX}] Logging worker error: {e}")
        finally:
            _log_queue.task_done()

def clear_logs() -> None:
    """Clear the active log file while keeping handlers intact."""
    log_file = _LOG_DIR / f"{LOG_NAME}.log"
    with open(log_file, "w", encoding="utf-8"):
        pass
    log_message(f"[INFO] [{PRINT_PREFIX}] Cleared active log file at {log_file}.")
