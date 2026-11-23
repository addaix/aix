# aix.claude_cli

A chat backend that runs prompts through the Claude Code CLI (`claude -p`).

With a Claude subscription and the CLI installed, `claude -p` answers prompts without
an API key, billed to the subscription. Use a model id with the `claude-cli/` prefix
and [`aix.chat()`](aix.html.md#aix.chat) / [`aix.complete()`](aix.html.md#aix.complete) route it here instead of to LiteLLM:

```default
>>> from aix import chat
>>> chat("Say hi in one word.", model="claude-cli/haiku")
'Hi!'
```

The CLI exposes no sampling controls, so `temperature`, `max_tokens`, `seed`,
`stream` and the like raise `ValueError` instead of being ignored in silence. The
cost the CLI reports is on `Completion.raw["total_cost_usd"]` (see
[`claude_cli_cost()`](#aix.claude_cli.claude_cli_cost)).

### Notes

`ANTHROPIC_API_KEY` and `ANTHROPIC_AUTH_TOKEN` are removed from the child
environment (the CLI would otherwise bill them, not the subscription); `--bare` is never used, since it skips
the keychain read that finds the subscription login; the call runs in a fresh private
temporary folder with
no tools, MCP servers, slash commands or session persistence.

### Module Attributes

| [`UNSUPPORTED_PARAMS`](#aix.claude_cli.UNSUPPORTED_PARAMS)   | refused, not dropped.   |
|-----------------------------------------------------------------------|-------------------------|

### Functions

| [`check_claude_cli`](#aix.claude_cli.check_claude_cli)()                              | Raise `RuntimeError` with an install hint when `claude` is not on PATH.                                                                                                                                            |
|--------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`claude_cli_complete`](#aix.claude_cli.claude_cli_complete)(messages, \*, model[, ...]) | Run `messages` through `claude -p` and return an [`aix.chat.Completion`](aix.html.md#aix.Completion).                                                                              |
| [`claude_cli_cost`](#aix.claude_cli.claude_cli_cost)(completion)                     | The cost in USD the CLI reported for `completion` (notional on a subscription).                                                                                                                                    |
| [`is_claude_cli_model`](#aix.claude_cli.is_claude_cli_model)(model)                      | Whether `model` names this backend.                                                                                                                                                                                |
| [`refuse_unsupported`](#aix.claude_cli.refuse_unsupported)(\*\*params)                  | Raise `ValueError` for any set parameter the CLI cannot honour: the named sampling controls, an `api_key`, and any other keyword (`top_p`, `stop`, `tools`...), which would otherwise be dropped in silence (#91). |

### aix.claude_cli.UNSUPPORTED_PARAMS *= ('temperature', 'max_tokens', 'seed', 'response_format', 'response_schema')*

refused, not dropped.

* **Type:**
  `chat`/`complete` arguments the CLI cannot honour

### aix.claude_cli.check_claude_cli()

Raise `RuntimeError` with an install hint when `claude` is not on PATH.

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

### aix.claude_cli.claude_cli_complete(messages, , model, timeout=600, cwd=None, extra_args=(), runner=None)

Run `messages` through `claude -p` and return an [`aix.chat.Completion`](aix.html.md#aix.Completion).

`model` is `"claude-cli/<name>"` (`haiku`, `sonnet`, `opus` or a full id).
`runner` is the `subprocess.run` seam (default: looked up at call time). A CLI error
(`is_error`, or a `terminal_reason` other than `completed`) raises `RuntimeError`.

### aix.claude_cli.claude_cli_cost(completion)

The cost in USD the CLI reported for `completion` (notional on a subscription).

* **Return type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float)

### aix.claude_cli.is_claude_cli_model(model)

Whether `model` names this backend.

```pycon
>>> is_claude_cli_model("claude-cli/haiku"), is_claude_cli_model("gpt-4o")
(True, False)
```

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

### aix.claude_cli.refuse_unsupported(\*\*params)

Raise `ValueError` for any set parameter the CLI cannot honour: the named
sampling controls, an `api_key`, and any other keyword (`top_p`, `stop`,
`tools`…), which would otherwise be dropped in silence (#91).

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)
