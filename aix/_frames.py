"""Find the user's frame: the first stack frame outside the aix package.

Two things need it: a ``DeprecationWarning`` must point at the line that called aix
(Python's default filters only show it when it is attributed to ``__main__`` or to the
test runner's code), and the opt-in call log (:mod:`aix.calllog`) records that line as
the caller. Both must hold however many aix frames sit in between (``aix.gen_ai.chat``
dispatching to a backend, a decorator stack, a ``contextlib`` wrapper), so they walk the
stack instead of counting a fixed number of levels.

>>> frame, level = first_external_frame()  # called from outside aix: this very frame
>>> level
1
"""

from __future__ import annotations

import contextlib
import os
import sys
from types import FrameType
from typing import Optional

#: Directory of the aix package: frames whose file lives under it are aix's own.
AIX_DIR = os.path.dirname(os.path.abspath(__file__)) + os.sep

#: Frames from these files are plumbing, never the caller (``contextlib`` wraps aix's
#: own context managers and decorators).
_PLUMBING = (os.path.abspath(contextlib.__file__),)


def is_internal(filename: str) -> bool:
    """Whether ``filename`` belongs to aix itself (or to plumbing that wraps it)."""
    path = os.path.abspath(filename)
    return path.startswith(AIX_DIR) or path in _PLUMBING


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
        if not is_internal(frame.f_code.co_filename):
            return frame, level
        frame = frame.f_back
        level += 1
    return None, level


def where(frame: Optional[FrameType]) -> str:
    """``file:line`` of ``frame``, or ``"?"`` for none."""
    if frame is None:
        return "?"
    return f"{os.path.abspath(frame.f_code.co_filename)}:{frame.f_lineno}"
