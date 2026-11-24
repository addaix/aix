"""An opt-in log of aix model calls: the resolved model, the caller, the outcome.

Off by default. Nothing is recorded unless a logger is installed, so a failing model
choice (a typo'd alias, a retired model, a missing key) can go unnoticed only when you
have not asked to see it. Three ways to turn it on, from narrowest to widest:

- per call, a keyword-only callback: ``chat("hi", on_call=print)``;
- per process or block, ``set_call_logger(fn)`` / ``with call_logger(fn): ...``;
- from the environment, ``AIX_CALL_LOG=/path/to/calls.jsonl`` writes one JSON line per
  call with :func:`jsonl_logger` (the prompt and the reply are never recorded).

A logger is any ``fn(record: CallRecord) -> None``. It runs after the call (for a stream,
when the stream ends), and an exception inside it is swallowed so logging can never break
a model call.

Logged entry points: ``chat``, ``complete`` (and what is built on them: ``sample``,
``batch_chat``, prompt functions...), ``describe_image``, ``compare_images``,
``embeddings`` / ``embed``, ``generate_image`` / ``generate_images`` / ``edit_image`` /
``create_variation``, ``text_to_speech``, ``transcribe`` (and
``transcribe_with_timestamps``) and ``translate_audio``. A call made on one of aix's own
worker pools records the line that called aix, not the pool's thread.

>>> seen = []
>>> with call_logger(seen.append):
...     with _record("chat", "gpt-x", None):
...         pass
>>> seen[0].function, seen[0].model, seen[0].ok
('chat', 'gpt-x', True)
"""

from __future__ import annotations

import concurrent.futures
import contextlib
import contextvars
import inspect
import json
import os
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import asdict, dataclass
from functools import wraps
from typing import Optional

from aix._frames import first_external_frame, where

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


#: The aix caller of the code submitting to one of aix's own worker pools (``batch_chat``,
#: ``sample(concurrency=...)``), carried into the worker through the copied context: in the
#: worker thread the stack above aix is the pool's machinery, not the user's code.
_submitter: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "aix_call_submitter", default=None
)

_THREADING = os.path.abspath(threading.__file__)
_FUTURES = os.path.dirname(os.path.abspath(concurrent.futures.__file__)) + os.sep


def _is_thread_machinery(filename: str) -> bool:
    path = os.path.abspath(filename)
    return path == _THREADING or path.startswith(_FUTURES)


def _caller() -> str:
    """``file:line`` of the first frame outside the aix package.

    In a worker of one of aix's own pools, where the first outside frame is the pool's
    thread machinery, it is the line that called aix in the submitting thread.
    """
    frame, _ = first_external_frame(skip=2)
    if frame is None or _is_thread_machinery(frame.f_code.co_filename):
        return _submitter.get() or where(frame)
    return where(frame)


def carry_caller(context: contextvars.Context) -> contextvars.Context:
    """Store the current caller in ``context``, a copy to run on another thread.

    aix's pools call this (through :func:`aix.config.submit_in_context`) in the submitting
    thread, so a call made in the worker is logged with the user's line.
    """
    caller = _caller()
    context.run(_submitter.set, caller)
    return context


class _Recording:
    """One call being recorded: :meth:`finish` sends its record, once."""

    def __init__(self, function: str, model: Optional[str], logger: CallLogger):
        self.function, self.model, self.logger = function, model, logger
        self.caller, self.start, self.time = _caller(), time.perf_counter(), time.time()
        self.done = False

    def finish(self, exc: Optional[BaseException] = None) -> None:
        if self.done:
            return
        self.done = True
        error = None if exc is None else f"{type(exc).__name__}: {exc}"
        with contextlib.suppress(Exception):
            self.logger(
                CallRecord(
                    function=self.function,
                    model=self.model,
                    caller=self.caller,
                    ok=error is None,
                    seconds=round(time.perf_counter() - self.start, 4),
                    error=error,
                    time=self.time,
                )
            )


def _start(
    function: str, model: Optional[str], explicit: Optional[CallLogger]
) -> Optional[_Recording]:
    logger = _active(explicit)
    return None if logger is None else _Recording(function, model, logger)


@contextlib.contextmanager
def _record(function: str, model: Optional[str], explicit: Optional[CallLogger]):
    """Record the call made inside the block to the active logger, if any."""
    recording = _start(function, model, explicit)
    if recording is None:
        yield
        return
    try:
        yield
    except BaseException as exc:
        recording.finish(exc)
        raise
    recording.finish()


class _LoggedStream:
    """A stream whose record is sent when it ends: exhausted, failed, closed or dropped.

    So an error raised while the stream is consumed is logged as a failure, and
    ``seconds`` covers the whole stream.
    """

    def __init__(self, stream: Iterator, recording: _Recording):
        self._stream, self._recording = stream, recording

    def __iter__(self):
        return self

    def __next__(self):
        try:
            return next(self._stream)
        except StopIteration:
            self._recording.finish()
            raise
        except BaseException as exc:
            self._recording.finish(exc)
            raise

    def close(self) -> None:
        with contextlib.suppress(Exception):
            close = getattr(self._stream, "close", None)
            if close is not None:
                close()
        self._recording.finish()

    def __del__(self):  # dropped unfinished (e.g. ``next(stream)`` then discarded)
        try:
            self._recording.finish()
        except Exception:  # noqa: BLE001 - e.g. at interpreter shutdown
            pass


def _resolved_model(sig, args, kwargs, default_model) -> Optional[str]:
    """The model a call will use: its ``model`` argument or the default, alias-resolved."""
    try:
        model = sig.bind_partial(*args, **kwargs).arguments.get("model")
    except TypeError:
        model = kwargs.get("model")
    try:
        from aix.config import resolve_model

        return resolve_model(model or (default_model() if default_model else None))
    except Exception:  # noqa: BLE001 - never let logging break a call
        return model


def logged(function: str, *, default_model: Optional[Callable[[], Optional[str]]] = None):
    """Decorator: record each call of an aix entry point to the opt-in call log.

    Adds the keyword-only ``on_call=`` seam: ``fn(CallRecord)``, called after the call
    with the resolved model, the caller and the outcome. Without it, nothing is recorded
    unless a logger was installed (:func:`set_call_logger`) or ``AIX_CALL_LOG`` is set.
    ``default_model`` returns the model the function uses when it is given none (read
    from the active config at call time). A lazy result (a generator, or the iterator a
    ``stream=True`` call returns) is recorded when it ends, so an error raised while it
    is consumed is logged as a failure.

    >>> @logged("echo")
    ... def echo(x, *, model=None):
    ...     return x
    >>> seen = []
    >>> echo("hi", model="gpt-x", on_call=seen.append)
    'hi'
    >>> seen[0].function, seen[0].model, seen[0].ok
    ('echo', 'gpt-x', True)
    """

    def decorate(func):
        sig = inspect.signature(func)

        @wraps(func)
        def wrapper(*args, on_call=None, **kwargs):
            if _active(on_call) is None:
                return func(*args, **kwargs)
            model = _resolved_model(sig, args, kwargs, default_model)
            recording = _start(function, model, on_call)
            try:
                result = func(*args, **kwargs)
            except BaseException as exc:
                recording.finish(exc)
                raise
            if inspect.isgenerator(result) or (
                kwargs.get("stream") and isinstance(result, Iterator)
            ):
                return _LoggedStream(result, recording)
            recording.finish()
            return result

        return wrapper

    return decorate
