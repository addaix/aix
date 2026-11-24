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
    import os

    return [os.path.basename(r.caller.rsplit(":", 1)[0]) for r in records]


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


def _sent_at_open_stream(monkeypatch, sent):
    """Patch chat's completion with one that 'sends' when called and returns an iterator."""
    import types

    def streaming(**kw):
        sent.append(1)
        return iter(
            [types.SimpleNamespace(choices=[types.SimpleNamespace(delta=types.SimpleNamespace(content=c))]) for c in "ab"]
        )

    monkeypatch.setattr(chat_module, "_completion", lambda: streaming)


@pytest.mark.parametrize(
    "act",
    [
        pytest.param(lambda s: None, id="never-iterated-dropped"),
        pytest.param(lambda s: s.close(), id="closed-before-first-chunk"),
        pytest.param(lambda s: next(s), id="one-chunk-then-dropped"),
    ],
)
def test_a_stream_closed_or_dropped_early_is_logged_once_as_ok(monkeypatch, act):
    """The request is sent when the stream opens, so it is logged however the stream ends."""
    import gc

    sent, records = [], []
    _sent_at_open_stream(monkeypatch, sent)
    stream = aix.chat("q", model="openai/gpt-4o-mini", stream=True, on_call=records.append)
    assert sent == [1] and records == []
    act(stream)
    del stream
    gc.collect()
    assert [(r.function, r.ok) for r in records] == [("chat", True)]
    assert _here(records) == ["test_calllog.py"]


def test_closing_an_unstarted_logged_stream_closes_the_stream():
    from aix.calllog import logged

    closed = []

    class Stream:
        def __iter__(self):
            return self

        def __next__(self):
            return 1

        def close(self):
            closed.append(True)

    @logged("g")
    def make(*, model=None, stream=True):
        return Stream()

    records = []
    s = make(model="m", stream=True, on_call=records.append)
    s.close()
    assert closed == [True]
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


def test_a_logged_lazy_result_stays_a_generator(monkeypatch):
    """Turning the log on must not change what a call returns."""
    import inspect
    import types

    embeddings_module = importlib.import_module("aix.embeddings")
    response = types.SimpleNamespace(data=[{"embedding": [0.1]}])
    monkeypatch.setattr(embeddings_module, "_embedding", lambda: lambda **kw: response)
    off = aix.embeddings(["x"], model="openai/text-embedding-3-small")
    with aix.call_logger(lambda r: None):
        on = aix.embeddings(["x"], model="openai/text-embedding-3-small")
    assert inspect.isgenerator(off) and inspect.isgenerator(on)
    assert on.send(None) == off.send(None) == [0.1]


def test_closing_a_logged_stream_propagates_the_streams_cleanup_error():
    from aix.calllog import logged

    def gen():
        try:
            yield 1
            yield 2
        finally:
            raise RuntimeError("cleanup failed")

    @logged("g")
    def make(*, model=None):
        return gen()

    records = []
    stream = make(model="m", on_call=records.append)
    next(stream)
    with pytest.raises(RuntimeError, match="cleanup failed"):
        stream.close()
    assert [(r.ok, r.error) for r in records] == [(False, "RuntimeError: cleanup failed")]


def test_a_logger_calling_aix_is_not_logged_again():
    records = []

    def logger(record):
        records.append(record)
        aix.chat("summarise the record", model="openai/gpt-4o-mini")  # no recursion

    aix.chat("hello", model="openai/gpt-4o-mini", on_call=logger)
    assert len(records) == 1


def test_submitting_to_a_pool_never_fails_on_caller_attribution(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    from aix import calllog
    from aix.config import submit_in_context

    def broken():
        raise FileNotFoundError("cwd is gone")

    monkeypatch.setattr(calllog, "_caller", broken)
    with ThreadPoolExecutor(1) as pool:
        assert submit_in_context(pool, lambda x: 2 * x, 3).result() == 6


def test_model_of_names_the_model_from_the_arguments():
    from aix.calllog import logged

    @logged("t", default_model=lambda: "default", model_of=lambda a: a.get("engine"))
    def transcribe_like(audio, *, engine=None, model=None):
        return "text"

    records = []
    transcribe_like(b"", engine="deepgram", on_call=records.append)
    transcribe_like(b"", model="openai/whisper-1", on_call=records.append)
    assert [r.model for r in records] == ["deepgram", "openai/whisper-1"]


def test_an_error_thrown_into_an_unstarted_logged_stream_is_logged_as_a_failure(monkeypatch):
    sent, records = [], []
    _sent_at_open_stream(monkeypatch, sent)
    stream = aix.chat("q", model="openai/gpt-4o-mini", stream=True, on_call=records.append)
    with pytest.raises(ValueError, match="stop"):
        stream.throw(ValueError("stop"))
    assert [(r.ok, r.error) for r in records] == [(False, "ValueError: stop")]


def _closable_stream_maker(closed):
    """A ``@logged`` maker returning a non-generator stream that notes when it is closed."""
    from aix.calllog import logged

    class Stream:
        def __iter__(self):
            return self

        def __next__(self):
            return 1

        def close(self):
            closed.append(True)

    @logged("g")
    def make(*, model=None, stream=True):
        return Stream()

    return make


def test_an_error_thrown_into_an_unstarted_logged_stream_closes_the_stream():
    """Like ``yield from``, a throw before the first chunk closes the stream (addaix/aix#102)."""
    closed, records = [], []
    s = _closable_stream_maker(closed)(model="m", stream=True, on_call=records.append)
    with pytest.raises(ValueError, match="stop"):
        s.throw(ValueError("stop"))
    assert closed == [True]
    assert [(r.ok, r.error) for r in records] == [(False, "ValueError: stop")]


def test_an_error_thrown_into_an_unstarted_logged_generator_finishes_it():
    from aix.calllog import logged

    ran = []

    def gen():
        ran.append(True)
        yield 1

    inner = gen()

    @logged("h")
    def make(*, model=None):
        return inner

    records = []
    s = make(model="m", on_call=records.append)
    with pytest.raises(ValueError, match="stop"):
        s.throw(ValueError("stop"))
    assert ran == [] and inner.gi_frame is None  # finished without running its body
    assert [(r.ok, r.error) for r in records] == [(False, "ValueError: stop")]


def test_a_first_non_none_send_raises_like_an_unstarted_generator():
    """``send(x)`` before the first chunk is a TypeError, not a dropped value (addaix/aix#102)."""
    closed, records = [], []
    s = _closable_stream_maker(closed)(model="m", stream=True, on_call=records.append)
    with pytest.raises(TypeError, match="just-started generator"):
        s.send(5)
    assert closed == [True]
    assert [(r.ok, r.error.split(":")[0]) for r in records] == [(False, "TypeError")]
    with pytest.raises(StopIteration):  # the stream ended with the error
        next(s)
    assert len(records) == 1


def test_a_first_send_of_none_starts_the_stream():
    closed, records = [], []
    s = _closable_stream_maker(closed)(model="m", stream=True, on_call=records.append)
    assert s.send(None) == 1
    s.close()
    assert closed == [True] and [r.ok for r in records] == [True]
