"""One place that announces the removal of the legacy ``aix.gen_ai`` chat backends.

The legacy backends (``openai_genai`` through ``oa``, ``google_genai`` through
``google-generativeai``) sit next to the litellm path that ``aix.chat`` uses. They are
deprecated, not deleted: calling one warns, naming its replacement and the version that
removes it. Importing ``aix`` stays silent.

The warning is attributed to the first frame outside aix, whichever entry point was used
(``openai_genai.chat``, ``aix.gen_ai.chat(prompt, model=...)``, ``chat_funcs[...]``), so
Python's default filters show it to a script calling aix.
"""

import warnings

from aix._frames import first_external_frame

#: The release that removes the legacy backends and the ``openai`` / ``google`` extras.
REMOVAL_VERSION = "0.1.0"


def warn_legacy_backend(name: str) -> None:
    """Emit the ``DeprecationWarning`` for the legacy backend ``name``, at the user's line."""
    _, stacklevel = first_external_frame()
    warnings.warn(
        f"the legacy aix.gen_ai {name!r} chat backend is deprecated and will be "
        f"removed in aix {REMOVAL_VERSION}; use aix.chat(prompt, model=...), which routes "
        f"through litellm (and drop the {name!r} extra).",
        DeprecationWarning,
        stacklevel=stacklevel,
    )
