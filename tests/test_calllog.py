"""The opt-in call log: off by default, one record per call with the resolved model, caller and outcome."""

import importlib
import json

import pytest

import aix

chat_module = importlib.import_module("aix.chat")
from aix.calllog import ENV_VAR


class _Msg:
    content = "hi"


class _Choice:
    message = _Msg()
    finish_reason = "stop"


class _Resp:
    choices = [_Choice()]
    model = "m"
    usage = None


@pytest.fixture(autouse=True)
def fake_completion(monkeypatch):
    monkeypatch.setattr(chat_module, "_completion", lambda: lambda **kw: _Resp())
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.delenv(ENV_VAR, raising=False)


def test_off_by_default_records_nothing(tmp_path):
    assert aix.chat("hello", model="openai/gpt-4o-mini") == "hi"


def test_on_call_gets_model_caller_and_outcome():
    records = []
    aix.chat("hello", model="openai/gpt-4o-mini", on_call=records.append)
    (r,) = records
    assert (r.function, r.model, r.ok, r.error) == ("chat", "openai/gpt-4o-mini", True, None)
    assert "test_calllog.py:" in r.caller
    assert "aix/chat.py" not in r.caller


def test_failure_is_recorded_and_still_raises(monkeypatch):
    def boom(**kw):
        raise RuntimeError("model retired")

    monkeypatch.setattr(chat_module, "_completion", lambda: boom)
    records = []
    with pytest.raises(RuntimeError, match="retired"):
        aix.chat("hello", model="openai/gpt-4o-mini", on_call=records.append)
    assert records[0].ok is False and "model retired" in records[0].error


def test_installed_logger_and_complete():
    records = []
    with aix.call_logger(records.append):
        aix.chat("a", model="openai/gpt-4o-mini")
        aix.complete("b", model="openai/gpt-4o-mini")
    assert [r.function for r in records] == ["chat", "complete"]
    aix.chat("c", model="openai/gpt-4o-mini")  # block exited: no more records
    assert len(records) == 2


def test_env_var_writes_one_json_line_per_call(tmp_path, monkeypatch):
    path = tmp_path / "calls.jsonl"
    monkeypatch.setenv(ENV_VAR, str(path))
    aix.chat("secret prompt", model="openai/gpt-4o-mini")
    aix.chat("again", model="openai/gpt-4o-mini")
    lines = [json.loads(l) for l in path.read_text().splitlines()]
    assert len(lines) == 2 and lines[0]["model"] == "openai/gpt-4o-mini"
    assert "secret prompt" not in path.read_text()


def test_a_broken_logger_never_breaks_the_call():
    def bad(record):
        raise ValueError("logger bug")

    assert aix.chat("hello", model="openai/gpt-4o-mini", on_call=bad) == "hi"
