"""A chat backend that runs prompts through the Claude Code CLI (``claude -p``).

With a Claude subscription and the CLI installed, ``claude -p`` answers prompts without
an API key, billed to the subscription. Use a model id with the ``claude-cli/`` prefix
and :func:`aix.chat` / :func:`aix.complete` route it here instead of to LiteLLM::

    >>> from aix import chat
    >>> chat("Say hi in one word.", model="claude-cli/haiku")  # doctest: +SKIP
    'Hi!'

The CLI exposes no sampling controls, so ``temperature``, ``max_tokens``, ``seed``,
``stream`` and the like raise ``ValueError`` instead of being ignored in silence. The
cost the CLI reports is on ``Completion.raw["total_cost_usd"]`` (see
:func:`claude_cli_cost`).

Notes: ``ANTHROPIC_API_KEY`` is removed from the child environment (the CLI would
otherwise bill that key, not the subscription); ``--bare`` is never used, since it skips
the keychain read that finds the subscription login; the call runs in a neutral cwd with
no tools, MCP servers, slash commands or session persistence.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from typing import Any, Callable, Iterable, Optional

CLAUDE_CLI_PREFIX = "claude-cli/"
CLAUDE_CLI_INSTALL_URL = "https://docs.claude.com/en/docs/claude-code/setup"

#: ``chat``/``complete`` arguments the CLI cannot honour: refused, not dropped.
UNSUPPORTED_PARAMS = (
    "temperature",
    "max_tokens",
    "seed",
    "response_format",
    "response_schema",
)


def is_claude_cli_model(model: Optional[str]) -> bool:
    """Whether ``model`` names this backend.

    >>> is_claude_cli_model("claude-cli/haiku"), is_claude_cli_model("gpt-4o")
    (True, False)
    """
    return isinstance(model, str) and model.startswith(CLAUDE_CLI_PREFIX)


def check_claude_cli() -> bool:
    """Raise ``RuntimeError`` with an install hint when ``claude`` is not on PATH."""
    if shutil.which("claude") is None:
        raise RuntimeError(
            "The `claude-cli/` models need the Claude Code CLI (`claude`) on your PATH. "
            f"Install it from {CLAUDE_CLI_INSTALL_URL}"
        )
    return True


def _split_messages(messages: Iterable[dict]) -> tuple[str, str]:
    """``(system, stdin_text)``: system turns joined; one user turn as-is, else a transcript."""
    system, turns = [], []
    for m in messages:
        content = m.get("content")
        text = (
            content
            if isinstance(content, str)
            else "".join(
                p.get("text", "") for p in (content or []) if isinstance(p, dict)
            )
        )
        (system if m.get("role") == "system" else turns).append((m.get("role"), text))
    if len(turns) == 1 and turns[0][0] == "user":
        stdin = turns[0][1]
    else:
        stdin = "\n\n".join(f"{role.capitalize()}: {text}" for role, text in turns)
    return "\n\n".join(t for _, t in system), stdin


def claude_cli_complete(
    messages: list[dict],
    *,
    model: str,
    timeout: float = 600,
    cwd: Optional[str] = None,
    extra_args: Iterable[str] = (),
    runner: Optional[Callable[..., Any]] = None,
):
    """Run ``messages`` through ``claude -p`` and return an :class:`aix.chat.Completion`.

    ``model`` is ``"claude-cli/<name>"`` (``haiku``, ``sonnet``, ``opus`` or a full id).
    ``runner`` is the ``subprocess.run`` seam (default: looked up at call time). A CLI error
    (``is_error``, or a ``terminal_reason`` other than ``completed``) raises ``RuntimeError``.
    """
    from aix.chat import Completion, Usage

    name = model[len(CLAUDE_CLI_PREFIX) :]
    system, stdin = _split_messages(messages)
    argv = [
        "claude", "-p", "--model", name, "--output-format", "json",
        "--no-session-persistence", "--tools", "", "--strict-mcp-config",
        "--disable-slash-commands", "--setting-sources", "project",
        *extra_args,
    ]  # fmt: skip
    if system:
        argv += ["--system-prompt", system]
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    proc = (runner or subprocess.run)(
        argv,
        input=stdin,
        capture_output=True,
        text=True,
        env=env,
        cwd=cwd or tempfile.gettempdir(),
        timeout=timeout,
    )
    try:
        data = json.loads(proc.stdout)
    except (TypeError, ValueError):
        raise RuntimeError(
            f"`claude -p` returned no JSON (exit {proc.returncode}): "
            f"{(proc.stderr or proc.stdout or '')[:300]!r}"
        ) from None
    if data.get("is_error") or data.get("terminal_reason") not in (None, "completed"):
        raise RuntimeError(
            f"{model}: {data.get('terminal_reason')} {str(data.get('result'))[:200]!r}"
        )
    u = data.get("usage") or {}
    prompt = int(u.get("input_tokens") or 0)
    cached = int(u.get("cache_read_input_tokens") or 0)
    created = int(u.get("cache_creation_input_tokens") or 0)
    out = int(u.get("output_tokens") or 0)
    return Completion(
        texts=(str(data.get("result", "")),),
        finish_reasons=("stop",),
        usage=Usage(
            prompt_tokens=prompt + cached + created,
            completion_tokens=out,
            total_tokens=prompt + cached + created + out,
            cached_prompt_tokens=cached,
            cache_creation_tokens=created,
        ),
        model=model,
        raw=data,
    )


def claude_cli_cost(completion) -> float:
    """The cost in USD the CLI reported for ``completion`` (notional on a subscription)."""
    raw = completion.raw if isinstance(completion.raw, dict) else {}
    return float(raw.get("total_cost_usd") or 0)


def refuse_unsupported(**params: Any) -> None:
    """Raise ``ValueError`` for any set parameter the CLI cannot honour."""
    set_ = [k for k in UNSUPPORTED_PARAMS if params.get(k) is not None]
    if params.get("stream"):
        set_.append("stream")
    if params.get("n", 1) != 1:
        set_.append("n")
    if set_:
        raise ValueError(
            f"claude-cli/ models cannot honour {', '.join(set_)}: the Claude Code CLI "
            "exposes no such control. Drop the argument, or use an API model."
        )
