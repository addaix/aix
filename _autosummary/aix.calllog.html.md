# aix.calllog

An opt-in log of aix model calls: the resolved model, the caller, the outcome.

Off by default. Nothing is recorded unless a logger is installed, so a failing model
choice (a typo’d alias, a retired model, a missing key) can go unnoticed only when you
have not asked to see it. Three ways to turn it on, from narrowest to widest:

- per call, a keyword-only callback: `chat("hi", on_call=print)`;
- per process or block, `set_call_logger(fn)` / `with call_logger(fn): ...`;
- from the environment, `AIX_CALL_LOG=/path/to/calls.jsonl` writes one JSON line per
  call with [`jsonl_logger()`](#aix.calllog.jsonl_logger) (the prompt and the reply are never recorded).

A logger is any `fn(record: CallRecord) -> None`. It runs after the call, and an
exception inside it is swallowed so logging can never break a model call.

```pycon
>>> seen = []
>>> with call_logger(seen.append):
...     with _record("chat", "gpt-x", None):
...         pass
>>> seen[0].function, seen[0].model, seen[0].ok
('chat', 'gpt-x', True)
```

### Module Attributes

| [`ENV_VAR`](#aix.calllog.ENV_VAR)   | Environment variable holding the path of a JSON-lines file; setting it enables logging.   |
|------------------------------------------------------------|-------------------------------------------------------------------------------------------|

### Functions

| [`set_call_logger`](#aix.calllog.set_call_logger)(logger)   | Install `logger` for this context (`None` turns logging off).   |
|----------------------------------------------------------------------------|-----------------------------------------------------------------|
| [`call_logger`](#aix.calllog.call_logger)(logger)       | Log calls made inside the `with` block to `logger`.             |
| [`jsonl_logger`](#aix.calllog.jsonl_logger)(path)        | A logger that appends one JSON line per call to `path`.         |

### Classes

| [`CallRecord`](#aix.calllog.CallRecord)(function, model, caller, ok, seconds)   | One aix call: which function, the model it resolved to, who called, how it ended.   |
|-----------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------|

### *class* aix.calllog.CallRecord(function, model, caller, ok, seconds, error=None, time=0.0)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One aix call: which function, the model it resolved to, who called, how it ended.

### aix.calllog.ENV_VAR *= 'AIX_CALL_LOG'*

Environment variable holding the path of a JSON-lines file; setting it enables logging.

### aix.calllog.call_logger(logger)

Log calls made inside the `with` block to `logger`.

* **Return type:**
  [`Iterator`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Iterator)[[`None`](https://docs.python.org/3/builtins/constants.html#None)]

### aix.calllog.jsonl_logger(path)

A logger that appends one JSON line per call to `path`.

* **Return type:**
  [`Callable`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable)[[[`CallRecord`](#aix.calllog.CallRecord)], [`None`](https://docs.python.org/3/builtins/constants.html#None)]

### aix.calllog.set_call_logger(logger)

Install `logger` for this context (`None` turns logging off).

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)
