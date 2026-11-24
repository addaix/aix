"""`import aix` must not import the optional `oa` package (issue #54).

Importing `oa` resolves an OpenAI key as a side effect: it raises without one,
and prompts on stdin in an interactive session. So `import aix` must not touch
it; the legacy backend imports it on first call.
"""

import os
import subprocess
import sys
import textwrap

FAKE_OA = textwrap.dedent(
    """
    raise RuntimeError("fake oa: imported at import time")
    """
)


def _run(tmp_path, code):
    pkg = tmp_path / "oa"
    pkg.mkdir()
    (pkg / "__init__.py").write_text(FAKE_OA)
    # Start from the real environment (Windows needs SYSTEMROOT etc. just to
    # start Python), minus any key, with the fake `oa` first on the path.
    env = {k: v for k, v in os.environ.items() if not k.endswith("_API_KEY")}
    env.update(
        HOME=str(tmp_path),
        USERPROFILE=str(tmp_path),
        PYTHONPATH=str(tmp_path),
        LITELLM_LOCAL_MODEL_COST_MAP="True",
    )
    return subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        stdin=subprocess.DEVNULL,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_import_aix_does_not_import_oa(tmp_path):
    result = _run(
        tmp_path,
        "import sys, aix; assert 'oa' not in sys.modules; "
        "assert 'gpt-4o' in aix.chat_models; print('ok')",
    )
    assert result.returncode == 0, result.stderr[-2000:]
    assert result.stdout.strip().endswith("ok")


def test_oa_imported_on_first_legacy_call(tmp_path):
    result = _run(
        tmp_path,
        "import aix.gen_ai as g\n"
        "try:\n"
        "    g.chat('hi', model='gpt-4o')\n"
        "except RuntimeError as e:\n"
        "    print('lazy:', e)\n",
    )
    assert result.returncode == 0, result.stderr[-2000:]
    assert "fake oa: imported at import time" in result.stdout


def test_passthrough_arguments(monkeypatch):
    """The lazy wrapper forwards every argument to oa.chat unchanged."""
    import types

    from aix.gen_ai import openai_genai

    if not hasattr(openai_genai, "chat"):
        import pytest

        pytest.skip("oa not installed")
    seen = {}
    fake = types.ModuleType("oa")
    fake.chat = lambda *a, **k: seen.update(args=a, kwargs=k) or "ok"
    monkeypatch.setitem(__import__("sys").modules, "oa", fake)
    assert openai_genai.chat(messages=[{"role": "user", "content": "x"}]) == "ok"
    assert seen == {
        "args": (),
        "kwargs": {"messages": [{"role": "user", "content": "x"}]},
    }


def test_legacy_openai_backend_warns_with_removal_version(monkeypatch):
    """A call through the legacy backend is deprecated, naming aix.chat and the removal release."""
    import sys
    import types

    import pytest

    from aix.gen_ai import openai_genai
    from aix.gen_ai._deprecation import REMOVAL_VERSION

    if not hasattr(openai_genai, "chat"):
        pytest.skip("oa not installed")
    fake = types.ModuleType("oa")
    fake.chat = lambda *a, **k: "ok"
    monkeypatch.setitem(sys.modules, "oa", fake)
    with pytest.warns(DeprecationWarning, match=f"removed in aix {REMOVAL_VERSION}.*aix.chat"):
        assert openai_genai.chat("hi") == "ok"


def test_importing_aix_emits_no_deprecation_warning(tmp_path):
    result = _run(tmp_path, "import warnings; warnings.filterwarnings('error', message='the legacy aix.gen_ai'); import aix; print('ok')")
    assert result.returncode == 0, result.stderr[-2000:]


def _legacy_warning_sites(call):
    """Run ``call`` and return the ``file`` of each legacy-backend DeprecationWarning."""
    import warnings

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        call()
    return [
        w.filename
        for w in caught
        if issubclass(w.category, DeprecationWarning) and "legacy aix.gen_ai" in str(w.message)
    ]


def test_legacy_warning_points_at_the_caller_for_every_entry_point(monkeypatch):
    """Whichever way the legacy backend is reached, the warning names the user's line.

    Python's default filters only show a DeprecationWarning attributed to ``__main__``
    (or to the test runner's code), so a warning attributed to an aix frame is hidden.
    """
    import sys
    import types

    import pytest

    import aix
    import aix.gen_ai as gen_ai
    from aix.gen_ai import openai_genai

    if not hasattr(openai_genai, "chat"):
        pytest.skip("oa not installed")
    fake = types.ModuleType("oa")
    fake.chat = lambda *a, **k: "ok"
    monkeypatch.setitem(sys.modules, "oa", fake)
    entry_points = {
        "openai_genai.chat": lambda: openai_genai.chat("hi"),
        "aix.gen_ai.chat": lambda: gen_ai.chat("hi", model="gpt-4o"),
        "chat_funcs[...]": lambda: aix.chat_funcs["gpt-4o"]("hi"),
        "chat_funcs.<id>": lambda: aix.chat_funcs.gpt_4o("hi"),
    }
    for label, call in entry_points.items():
        assert _legacy_warning_sites(call) == [__file__], label


def test_legacy_google_warning_points_at_the_caller(monkeypatch):
    import types

    import pytest

    import aix.gen_ai as gen_ai

    google_genai = pytest.importorskip("aix.gen_ai.google_genai")
    if not hasattr(google_genai, "chat"):
        pytest.skip("google-generativeai not installed")

    class FakeModel:
        def __init__(self, model):
            pass

        def generate_content(self, prompt):
            return types.SimpleNamespace(text="ok")

    monkeypatch.setattr(google_genai.genai, "GenerativeModel", FakeModel)
    assert _legacy_warning_sites(lambda: google_genai.chat("hi")) == [__file__]
    assert _legacy_warning_sites(
        lambda: gen_ai.chat("hi", model="gemini-1.5-flash")
    ) == [__file__]
