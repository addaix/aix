"""prompt_func keeps escaped braces and builds for keyword-named fields (addaix/aix#93)."""

import aix.prompts as prompts
from aix.prompts import prompt_func


def test_escaped_braces_survive_formatting(monkeypatch):
    monkeypatch.setattr(prompts, "chat", lambda prompt, **kw: prompt)
    f = prompt_func("Write {name}. Use {{braces}} here.")
    assert f(name="x") == "Write x. Use {braces} here."


def test_a_keyword_named_field_builds_and_is_callable(monkeypatch):
    import inspect

    monkeypatch.setattr(prompts, "chat", lambda prompt, **kw: prompt)
    f = prompt_func("Describe the {class} of {x}")
    assert f(**{"class": "mammal", "x": "cats"}) == "Describe the mammal of cats"
    assert "class" not in inspect.signature(f).parameters  # plain (**kwargs)


def test_identifier_fields_still_get_a_signature():
    import inspect

    f = prompt_func("Greet {name} in {language:English}")
    assert list(inspect.signature(f).parameters) == ["name", "language"]
