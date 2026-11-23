"""One place that announces the removal of the legacy ``aix.gen_ai`` chat backends.

The legacy backends (``openai_genai`` through ``oa``, ``google_genai`` through
``google-generativeai``) sit next to the litellm path that ``aix.chat`` uses. They are
deprecated, not deleted: calling one warns, naming its replacement and the version that
removes it. Importing ``aix`` stays silent.
"""

import warnings

#: The release that removes the legacy backends and the ``openai`` / ``google`` extras.
REMOVAL_VERSION = "0.1.0"


def warn_legacy_backend(name: str, *, stacklevel: int = 3) -> None:
    """Emit the ``DeprecationWarning`` for the legacy backend ``name``."""
    warnings.warn(
        f"the legacy aix.gen_ai {name!r} chat backend is deprecated and will be "
        f"removed in aix {REMOVAL_VERSION}; use aix.chat(prompt, model=...), which routes "
        f"through litellm (and drop the {name!r} extra).",
        DeprecationWarning,
        stacklevel=stacklevel,
    )
