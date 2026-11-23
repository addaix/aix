"""The claude-cli/ backend: routing, argv, refusal of unsupported params, errors."""

import json
import subprocess

import pytest

import aix
from aix import claude_cli


def _reply(**over):
    data = {
        "result": "hello",
        "total_cost_usd": 0.0123,
        "usage": {"input_tokens": 3, "output_tokens": 2, "cache_read_input_tokens": 5},
        **over,
    }
    return json.dumps(data)


@pytest.fixture()
def fake_cli(monkeypatch):
    calls = []

    def run(argv, **kw):
        calls.append((argv, kw))
        return subprocess.CompletedProcess(argv, 0, stdout=_reply(), stderr="")

    monkeypatch.setattr(claude_cli.shutil, "which", lambda _: "/usr/bin/claude")
    monkeypatch.setattr(claude_cli.subprocess, "run", run)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-must-not-leak")
    return calls


def test_chat_routes_to_the_cli(fake_cli):
    assert aix.chat("hi", model="claude-cli/haiku") == "hello"
    argv, kw = fake_cli[0]
    assert argv[:4] == ["claude", "-p", "--model", "haiku"]
    assert "--bare" not in argv and "--no-session-persistence" in argv
    assert kw["input"] == "hi"
    assert "ANTHROPIC_API_KEY" not in kw["env"]


def test_complete_returns_usage_and_cost(fake_cli):
    c = aix.complete(
        [{"role": "system", "content": "Be brief."}, {"role": "user", "content": "hi"}],
        model="claude-cli/sonnet",
    )
    assert c.text == "hello" and c.finish_reason == "stop"
    assert c.usage.prompt_tokens == 8 and c.usage.cached_prompt_tokens == 5
    assert claude_cli.claude_cli_cost(c) == pytest.approx(0.0123)
    argv = fake_cli[0][0]
    assert argv[argv.index("--system-prompt") + 1] == "Be brief."


@pytest.mark.parametrize(
    "kw", [{"temperature": 0.2}, {"max_tokens": 5}, {"stream": True}]
)
def test_unsupported_params_are_refused(fake_cli, kw):
    with pytest.raises(ValueError, match="cannot honour"):
        aix.chat("hi", model="claude-cli/haiku", **kw)
    assert not fake_cli


def test_cli_errors_raise(fake_cli, monkeypatch):
    monkeypatch.setattr(
        claude_cli.subprocess,
        "run",
        lambda argv, **kw: subprocess.CompletedProcess(
            argv, 0, stdout=_reply(is_error=True, result="boom"), stderr=""
        ),
    )
    with pytest.raises(RuntimeError, match="boom"):
        aix.chat("hi", model="claude-cli/haiku")


def test_missing_cli_has_an_install_hint(monkeypatch):
    monkeypatch.setattr(claude_cli.shutil, "which", lambda _: None)
    with pytest.raises(RuntimeError, match="Claude Code CLI"):
        aix.chat("hi", model="claude-cli/haiku")


def test_multi_turn_becomes_a_transcript():
    system, stdin = claude_cli._split_messages(
        [
            {"role": "user", "content": "a"},
            {"role": "assistant", "content": "b"},
            {"role": "user", "content": "c"},
        ]
    )
    assert system == "" and stdin == "User: a\n\nAssistant: b\n\nUser: c"
