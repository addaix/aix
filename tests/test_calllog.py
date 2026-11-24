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


def _here(records):
    """The callers of ``records``, reduced to this test file's name (or the full path)."""
    return [r.caller.rsplit("/", 1)[-1].split(":")[0] for r in records]


def test_calls_on_aix_worker_pools_record_the_user_line():
    """batch_chat / sample(concurrency>1) run on aix's pools: the caller is still this file."""
    records = []
    with aix.call_logger(records.append):
        list(aix.batch_chat(["a", "b"], model="openai/gpt-4o-mini", max_workers=2))
        aix.sample("q", n=3, model="openai/gpt-4o-mini", concurrency=3)
    assert len(records) == 5
    assert set(_here(records)) == {"test_calllog.py"}, [r.caller for r in records]


def test_an_error_raised_while_a_stream_is_consumed_is_logged_as_a_failure(monkeypatch):
    import types

    def streaming(**kw):
        def chunks():
            yield types.SimpleNamespace(
                choices=[types.SimpleNamespace(delta=types.SimpleNamespace(content="a"))]
            )
            raise RuntimeError("stream died")

        return chunks()

    monkeypatch.setattr(chat_module, "_completion", lambda: streaming)
    records = []
    stream = aix.chat("q", model="openai/gpt-4o-mini", stream=True, on_call=records.append)
    assert records == []  # recorded when the stream ends, not when it opens
    with pytest.raises(RuntimeError, match="stream died"):
        "".join(stream)
    (r,) = records
    assert r.ok is False and "stream died" in r.error
    assert _here(records) == ["test_calllog.py"]


def test_a_stream_consumed_to_the_end_is_logged_once_as_ok(monkeypatch):
    import types

    def streaming(**kw):
        return iter(
            [types.SimpleNamespace(choices=[types.SimpleNamespace(delta=types.SimpleNamespace(content=c))]) for c in "ab"]
        )

    monkeypatch.setattr(chat_module, "_completion", lambda: streaming)
    records = []
    assert "".join(aix.chat("q", model="openai/gpt-4o-mini", stream=True, on_call=records.append)) == "ab"
    assert [r.ok for r in records] == [True]


def test_vision_calls_are_logged(monkeypatch):
    vision_module = importlib.import_module("aix.vision")
    monkeypatch.setattr(vision_module, "_completion", lambda: lambda **kw: _Resp())
    records = []
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 20
    with aix.call_logger(records.append):
        assert aix.describe_image(png, model="openai/gpt-4o-mini") == "hi"
    assert [(r.function, r.model, r.ok) for r in records] == [
        ("describe_image", "openai/gpt-4o-mini", True)
    ]
    assert _here(records) == ["test_calllog.py"]


def test_embeddings_are_logged_with_the_default_model(monkeypatch):
    import types

    from aix import config

    embeddings_module = importlib.import_module("aix.embeddings")
    response = types.SimpleNamespace(data=[{"embedding": [0.1, 0.2]}])
    monkeypatch.setattr(embeddings_module, "_embedding", lambda: lambda **kw: response)
    records = []
    with aix.call_logger(records.append):
        assert aix.embed("hi") == [0.1, 0.2]
    (r,) = records
    assert (r.function, r.ok) == ("embeddings", True)
    assert r.model == config.resolve_model(config.get_config().embeddings.model)
    assert _here(records) == ["test_calllog.py"]


def test_logged_entry_points_keep_their_signature():
    import inspect

    assert "model" in inspect.signature(aix.describe_image).parameters
    assert "on_call" not in inspect.signature(aix.chat).parameters


def test_audio_calls_are_logged_once(monkeypatch):
    audio_module = importlib.import_module("aix.audio")
    monkeypatch.setattr(audio_module, "_litellm_speech", lambda **kw: b"audio")
    monkeypatch.setattr(audio_module, "_litellm_transcription", lambda **kw: {"text": "hello"})
    records = []
    with aix.call_logger(records.append):
        aix.text_to_speech("hi", model="openai/tts-1")
        aix.transcribe(b"RIFF....", model="openai/whisper-1")
    assert [(r.function, r.model, r.ok) for r in records] == [
        ("text_to_speech", "openai/tts-1", True),
        ("transcribe", "openai/whisper-1", True),
    ]
    assert set(_here(records)) == {"test_calllog.py"}
