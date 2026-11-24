"""Find the user's frame: the first stack frame outside the aix package.

Two things need it: a ``DeprecationWarning`` must point at the line that called aix
(Python's default filters only show it when it is attributed to ``__main__`` or to the
test runner's code), and the opt-in call log (:mod:`aix.calllog`) records that line as
the caller. Both must hold however many aix frames sit in between (``aix.gen_ai.chat``
dispatching to a backend, a decorator stack, a ``contextlib`` wrapper), so they walk the
stack instead of counting a fixed number of levels.

Frames are classified by the module they run in (``frame.f_globals['__name__']``), not
by file path: no filesystem call (a deleted working directory cannot break it), and it
holds for frozen builds whose code objects carry relative file names.

>>> is_internal_module('aix.chat'), is_internal_module('contextlib'), is_internal_module('aixy')
(True, True, False)
"""

from __future__ import annotations

import os
import sys
from types import FrameType
from typing import Optional

#: Modules whose frames are plumbing around aix, never the caller (``contextlib`` wraps
#: aix's own context managers and decorators).
_PLUMBING = frozenset({"contextlib"})

#: Modules of the thread machinery a pool worker runs on.
_THREAD_MACHINERY = ("threading", "concurrent.futures")


def _module(frame: FrameType) -> str:
    return frame.f_globals.get("__name__") or ""


def _in(module: str, packages) -> bool:
    return any(module == p or module.startswith(p + ".") for p in packages)


def is_internal_module(module: str) -> bool:
    """Whether code of ``module`` belongs to aix itself (or to plumbing that wraps it)."""
    return _in(module, ("aix",)) or module in _PLUMBING


def is_thread_machinery(frame: Optional[FrameType]) -> bool:
    """Whether ``frame`` is a thread pool's or ``threading``'s own code."""
    return frame is not None and _in(_module(frame), _THREAD_MACHINERY)


def first_external_frame(*, skip: int = 1) -> tuple[Optional[FrameType], int]:
    """The first frame outside aix, and its ``stacklevel`` relative to the caller.

    The walk starts ``skip`` frames above this function (``skip=1``: the function that
    called ``first_external_frame``). The returned level counts like
    :func:`warnings.warn`'s ``stacklevel`` from that starting frame: 1 is the starting
    frame itself, 2 its caller, and so on. ``(None, level)`` when every frame is aix's.
    """
    frame = sys._getframe(skip)
    level = 1
    while frame is not None:
        if not is_internal_module(_module(frame)):
            return frame, level
        frame = frame.f_back
        level += 1
    return None, level


def where(frame: Optional[FrameType]) -> str:
    """``file:line`` of ``frame`` (absolute when it can be), or ``"?"`` for none."""
    if frame is None:
        return "?"
    filename = frame.f_code.co_filename
    try:
        filename = os.path.abspath(filename)
    except OSError:  # e.g. a relative name while the working directory is gone
        pass
    return f"{filename}:{frame.f_lineno}"
