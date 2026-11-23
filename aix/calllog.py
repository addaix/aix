"""An opt-in log of aix model calls: the resolved model, the caller, the outcome.

Off by default. Nothing is recorded unless a logger is installed, so a failing model
choice (a typo'd alias, a retired model, a missing key) can go unnoticed only when you
have not asked to see it. Three ways to turn it on, from narrowest to widest:

- per call, a keyword-only callback: ``chat("hi", on_call=print)``;
- per process or block, ``set_call_logger(fn)`` / ``with call_logger(fn): ...``;
- from the environment, ``AIX_CALL_LOG=/path/to/calls.jsonl`` writes one JSON line per
  call with :func:`jsonl_logger` (the prompt and the reply are never recorded).

A logger is any ``fn(record: CallRecord) -> None``. It runs after the call, and an
exception inside it is swallowed so logging can never break a model call.

>>> seen = []
>>> with call_logger(seen.append):
...     with _record("chat", "gpt-x", None):
...         pass
>>> seen[0].function, seen[0].model, seen[0].ok
('chat', 'gpt-x', True)
"""

from __future__ import annotations

import contextlib
import contextvars
import json
import os
import sys
import time
from collections.abc import Callable, Iterator
from dataclasses import asdict, dataclass
from typing import Optional

__all__ = ["CallRecord", "set_call_logger", "call_logger", "jsonl_logger", "ENV_VAR"]

#: Environment variable holding the path of a JSON-lines file; setting it enables logging.
ENV_VAR = "AIX_CALL_LOG"

CallLogger = Callable[["CallRecord"], None]

_logger: contextvars.ContextVar[Optional[CallLogger]] = contextvars.ContextVar(
    "aix_call_logger", default=None
)


@dataclass(frozen=True)
class CallRecord:
    """One aix call: which function, the model it resolved to, who called, how it ended."""

    function: str
    model: Optional[str]
    caller: str
    ok: bool
    seconds: float
    error: Optional[str] = None
    time: float = 0.0


def jsonl_logger(path: str | os.PathLike) -> CallLogger:
    """A logger that appends one JSON line per call to ``path``."""

    def log(record: CallRecord) -> None:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(record)) + "\n")

    return log


def set_call_logger(logger: Optional[CallLogger]) -> None:
    """Install ``logger`` for this context (``None`` turns logging off)."""
    _logger.set(logger)


@contextlib.contextmanager
def call_logger(logger: Optional[CallLogger]) -> Iterator[None]:
    """Log calls made inside the ``with`` block to ``logger``."""
    token = _logger.set(logger)
    try:
        yield
    finally:
        _logger.reset(token)


def _active(explicit: Optional[CallLogger]) -> Optional[CallLogger]:
    if explicit is not None:
        return explicit
    installed = _logger.get()
    if installed is not None:
        return installed
    path = os.environ.get(ENV_VAR)
    return jsonl_logger(path) if path else None


def _caller() -> str:
    """``file:line`` of the first frame outside the aix package."""
    package = os.path.dirname(os.path.abspath(__file__))
    frame = sys._getframe(1)
    while frame is not None:
        filename = os.path.abspath(frame.f_code.co_filename)
        if not filename.startswith(package) and "contextlib" not in filename:
            return f"{filename}:{frame.f_lineno}"
        frame = frame.f_back
    return "?"


@contextlib.contextmanager
def _record(function: str, model: Optional[str], explicit: Optional[CallLogger]):
    """Record the call made inside the block to the active logger, if any."""
    logger = _active(explicit)
    if logger is None:
        yield
        return
    caller, start, now = _caller(), time.perf_counter(), time.time()
    error = None
    try:
        yield
    except BaseException as exc:
        error = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        with contextlib.suppress(Exception):
            logger(
                CallRecord(
                    function=function,
                    model=model,
                    caller=caller,
                    ok=error is None,
                    seconds=round(time.perf_counter() - start, 4),
                    error=error,
                    time=now,
                )
            )
