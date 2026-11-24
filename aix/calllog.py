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
worker pools records the line that called aix, not the pool's thread; one handed
straight to a thread or pool of your own (``pool.submit(aix.chat, ...)``) records ``"?"``
(and is only logged there if the logger reaches that thread: ``AIX_CALL_LOG``, or a
copied context).

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
import inspect
import json
import os
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import asdict, dataclass
from functools import wraps
from typing import Optional

from aix._frames import first_external_frame, is_thread_machinery, where

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

#: Set while a logger runs: a model call made by a logger is not logged (no recursion).
_in_logger: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "aix_in_call_logger", default=False
)


def _caller() -> str:
    """``file:line`` of the first frame outside the aix package.

    In a worker of one of aix's own pools (or anything submitted through
    :func:`aix.config.submit_in_context`), where the first outside frame is the pool's
    thread machinery, it is the line that called aix in the submitting thread. A call
    handed straight to a thread or pool of your own (``pool.submit(aix.chat, ...)``) has
    no line of yours on its stack: its caller is ``"?"``.
    """
    frame, _ = first_external_frame(skip=2)
    if frame is None or is_thread_machinery(frame):
        return _submitter.get() or "?"
    return where(frame)


def carry_caller(context: contextvars.Context) -> contextvars.Context:
    """Store the current caller in ``context``, a copy to run on another thread.

    aix's pools call this (through :func:`aix.config.submit_in_context`) in the submitting
    thread, so a call made in the worker is logged with the user's line. It never fails:
    on any error the context is returned as it is.
    """
    try:
        caller = _caller()
        context.run(_submitter.set, caller)
    except Exception:  # noqa: BLE001 - attribution must never break a submit
        pass
    return context


class _Recording:
    """One call being recorded: :meth:`finish` sends its record, once (thread-safe)."""

    def __init__(self, function: str, model: Optional[str], logger: CallLogger):
        self.function, self.model, self.logger = function, model, logger
        self.caller, self.start, self.time = _caller(), time.perf_counter(), time.time()
        self._lock = threading.Lock()
        self.done = False

    def finish(self, exc: Optional[BaseException] = None) -> None:
        with self._lock:
            if self.done:
                return
            self.done = True
        error = None if exc is None else f"{type(exc).__name__}: {exc}"
        token = _in_logger.set(True)
        try:
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
        except Exception:  # noqa: BLE001 - logging can never break a model call
            pass
        finally:
            _in_logger.reset(token)


def _start(
    function: str, model: Optional[str], explicit: Optional[CallLogger]
) -> Optional[_Recording]:
    logger = None if _in_logger.get() else _active(explicit)
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


def _close_unstarted(stream: Iterator, recording: _Recording, exc=None) -> None:
    """Close a ``stream`` that was never delegated to, then record ``exc`` (``None``: ok).

    An error raised while closing is recorded instead, and propagates.
    """
    try:
        close = getattr(stream, "close", None)
        if close is not None:
            close()
    except BaseException as close_exc:
        recording.finish(close_exc)
        raise
    recording.finish(exc)


def _logged_stream(stream: Iterator, recording: _Recording):
    """Yield from ``stream`` and send the record when it ends.

    Exhausted: ok. Raised: the error. Closed early or dropped (``close()``, or garbage
    collection of an unfinished stream), before or after its first item: ok, at that
    moment. It is a generator, so ``send``, ``throw`` and ``close`` reach ``stream`` as
    they would without logging.

    The generator returned is already started (see :func:`_started_logged_stream`):
    closing or collecting a generator that never ran skips its body, and the request
    was sent when the stream opened, so a stream nobody read must still be recorded.
    Until its first item it behaves as an unstarted generator would: ``throw(exc)``
    closes ``stream`` and raises ``exc`` (what ``yield from`` does to a stream that
    never started), and ``send(x)`` with ``x`` not ``None`` raises ``TypeError``,
    closing ``stream`` and ending the logged stream with that error. Either way the
    call is recorded once.
    """
    try:
        sent = yield  # the priming step: from here on, close() and collection run the handlers
    except GeneratorExit:
        # Closed before its first item: ``stream`` was never delegated to, so close it.
        _close_unstarted(stream, recording)
        raise
    except BaseException as exc:  # thrown in before the first item
        _close_unstarted(stream, recording, exc)
        raise
    if sent is not None:
        exc = TypeError("can't send non-None value to a just-started generator")
        _close_unstarted(stream, recording, exc)
        raise exc
    try:
        result = yield from stream
    except GeneratorExit:
        recording.finish()
        raise
    except BaseException as exc:
        recording.finish(exc)
        raise
    recording.finish()
    return result


def _started_logged_stream(stream: Iterator, recording: _Recording):
    """:func:`_logged_stream`, advanced past its priming step (``stream`` is untouched)."""
    logged_stream = _logged_stream(stream, recording)
    next(logged_stream)
    return logged_stream


def _resolved_model(sig, args, kwargs, default_model, model_of) -> Optional[str]:
    """The model a call will use: its ``model`` argument or the default, alias-resolved."""
    try:
        arguments = sig.bind_partial(*args, **kwargs).arguments
    except TypeError:
        arguments = dict(kwargs)
    model = arguments.get("model")
    if model_of is not None:
        with contextlib.suppress(Exception):
            chosen = model_of(arguments)
            if chosen is not None:
                return chosen
    try:
        from aix.config import resolve_model

        return resolve_model(model or (default_model() if default_model else None))
    except Exception:  # noqa: BLE001 - never let logging break a call
        return model


def logged(
    function: str,
    *,
    default_model: Optional[Callable[[], Optional[str]]] = None,
    model_of: Optional[Callable[[dict], Optional[str]]] = None,
):
    """Decorator: record each call of an aix entry point to the opt-in call log.

    Adds the keyword-only ``on_call=`` seam: ``fn(CallRecord)``, called after the call
    with the resolved model, the caller and the outcome. Without it, nothing is recorded
    unless a logger was installed (:func:`set_call_logger`) or ``AIX_CALL_LOG`` is set.
    ``default_model`` returns the model the function uses when it is given none (read
    from the active config at call time); ``model_of(arguments)``, when given, names the
    model from the call's bound arguments instead (``None``: fall back to the above). The
    model is resolved when the call is made. A lazy result (a generator, or the iterator a
    ``stream=True`` call returns) is recorded when it ends, so an error raised while it
    is consumed is logged as a failure, and one closed or dropped unread is still logged;
    it stays a generator (``send``, ``throw`` and
    ``close`` pass through). A model call made from inside a logger is not logged.

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
            if _in_logger.get() or _active(on_call) is None:
                return func(*args, **kwargs)
            model = _resolved_model(sig, args, kwargs, default_model, model_of)
            recording = _start(function, model, on_call)
            if recording is None:
                return func(*args, **kwargs)
            try:
                result = func(*args, **kwargs)
            except BaseException as exc:
                recording.finish(exc)
                raise
            if inspect.isgenerator(result) or (
                kwargs.get("stream") and isinstance(result, Iterator)
            ):
                return _started_logged_stream(result, recording)
            recording.finish()
            return result

        return wrapper

    return decorate
