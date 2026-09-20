"""
Structured logging configuration.

Keeps log output consistent and machine-parseable, and ensures internal
exception details never leak into user-facing API responses (see
app/main.py exception handlers).
"""
import logging
import sys


def configure_logging(debug: bool = True) -> None:
    level = logging.DEBUG if debug else logging.INFO
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers = [handler]

    # Quiet noisy third-party loggers unless we're debugging.
    for noisy in ("uvicorn.access", "httpx"):
        logging.getLogger(noisy).setLevel(logging.WARNING if not debug else logging.INFO)
