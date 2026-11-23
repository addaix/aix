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

Notes: ``ANTHROPIC_API_KEY`` and ``ANTHROPIC_AUTH_TOKEN`` are removed from the child
environment (the CLI would otherwise bill them, not the subscription); ``--bare`` is never used, since it skips
the keychain read that finds the subscription login; the call runs in a fresh private
temporary folder with
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

#: Environment variables removed from the ``claude`` child: either one would bill the API.
_API_CREDENTIAL_VARS = frozenset({"ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"})

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
        if isinstance(content, str) or content is None:
            text = content or ""
        else:
            parts = list(content)
            other = [
                p
                for p in parts
                if not (isinstance(p, dict) and p.get("type", "text") == "text")
            ]
            if other:  # an image or audio part would be dropped in silence (#91)
                kinds = sorted(
                    {
                        str(p.get("type")) if isinstance(p, dict) else type(p).__name__
                        for p in other
                    }
                )
                raise ValueError(
                    f"claude-cli/ models take text only; this message has {', '.join(kinds)} "
                    "content. Use an API model for it."
                )
            text = "".join(p.get("text", "") for p in parts)
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
    if not name or name.startswith("-") or any(c.isspace() for c in name):
        raise ValueError(
            f"Not a claude-cli/ model name: {name!r} (e.g. 'haiku', 'opus')"
        )
    system, stdin = _split_messages(messages)
    argv = [
        "claude", "-p", "--model", name, "--output-format", "json",
        "--no-session-persistence", "--tools", "", "--strict-mcp-config",
        "--disable-slash-commands", "--setting-sources", "project",
        *extra_args,
    ]  # fmt: skip
    if system:
        argv += ["--system-prompt", system]
    # Both credentials would make the CLI bill the API rather than the subscription.
    env = {k: v for k, v in os.environ.items() if k not in _API_CREDENTIAL_VARS}
    # A fresh private folder, not the shared temp dir: with --setting-sources project,
    # a .claude/settings.json someone planted there would be loaded (#91).
    with tempfile.TemporaryDirectory(prefix="aix-claude-cli-") as neutral:
        proc = (runner or subprocess.run)(
            argv,
            input=stdin,
            capture_output=True,
            text=True,
            env=env,
            cwd=cwd or neutral,
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
    """Raise ``ValueError`` for any set parameter the CLI cannot honour: the named
    sampling controls, an ``api_key``, and any other keyword (``top_p``, ``stop``,
    ``tools``...), which would otherwise be dropped in silence (#91)."""
    known = {*UNSUPPORTED_PARAMS, "stream", "n", "api_key", "max_repairs"}
    set_ = [k for k in UNSUPPORTED_PARAMS if params.get(k) is not None]
    set_ += [k for k in ("api_key", "max_repairs") if params.get(k) is not None]
    set_ += [k for k, v in params.items() if k not in known and v is not None]
    if params.get("stream"):
        set_.append("stream")
    if params.get("n", 1) != 1:
        set_.append("n")
    if set_:
        raise ValueError(
            f"claude-cli/ models cannot honour {', '.join(set_)}: the Claude Code CLI "
            "exposes no such control. Drop the argument, or use an API model."
        )
