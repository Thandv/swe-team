"""Backend selection + structural translation tests.

We don't hit any LLM API here. We only verify that:
  - make_backend dispatches correctly on name
  - Missing API key for a chosen backend fails cleanly (not a stack trace)
  - The Gemini backend translates our universal tool/message format into the
    types the google-genai SDK actually expects.

Live API behavior is intentionally not tested here — it's covered by the
end-to-end verification when an API key is available.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

DRIVER_PARENT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DRIVER_PARENT))


def _install_placeholder_keys(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setenv("ANTHROPIC_API_KEY", "placeholder-no-real-call")


def test_make_backend_anthropic(monkeypatch) -> None:  # noqa: ANN001
    _install_placeholder_keys(monkeypatch)
    from orchestrator_driver import AnthropicBackend, make_backend
    backend = make_backend("anthropic")
    assert isinstance(backend, AnthropicBackend)
    assert backend.name == "anthropic"


def test_make_backend_gemini_without_key_exits(monkeypatch) -> None:  # noqa: ANN001
    _install_placeholder_keys(monkeypatch)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    from orchestrator_driver import make_backend
    try:
        make_backend("gemini")
    except SystemExit as e:
        assert e.code == 1
    else:
        raise AssertionError("expected SystemExit when GEMINI_API_KEY missing")


def test_make_backend_gemini_with_key(monkeypatch) -> None:  # noqa: ANN001
    _install_placeholder_keys(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "placeholder")
    from orchestrator_driver import GeminiBackend, make_backend
    backend = make_backend("gemini")
    assert isinstance(backend, GeminiBackend)
    assert backend.name == "gemini"


def test_make_backend_unknown_exits(monkeypatch) -> None:  # noqa: ANN001
    _install_placeholder_keys(monkeypatch)
    from orchestrator_driver import make_backend
    try:
        make_backend("garbage-llm")
    except SystemExit as e:
        assert e.code == 1
    else:
        raise AssertionError("expected SystemExit for unknown backend")


def test_make_backend_default_from_env(monkeypatch) -> None:  # noqa: ANN001
    _install_placeholder_keys(monkeypatch)
    monkeypatch.delenv("LLM_BACKEND", raising=False)
    from orchestrator_driver import AnthropicBackend, make_backend
    assert isinstance(make_backend(), AnthropicBackend)


def test_gemini_tool_translation(monkeypatch) -> None:  # noqa: ANN001
    _install_placeholder_keys(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "placeholder")
    from orchestrator_driver import make_backend
    backend = make_backend("gemini")
    tools = [
        {
            "name": "read_file",
            "description": "read a file under the project root",
            "input_schema": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
        {
            "name": "bash",
            "description": "run a bash command",
            "input_schema": {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
        },
    ]
    gtools = backend._to_gemini_tools(tools)
    assert len(gtools) == 1, "expect one Tool aggregate containing all declarations"
    decls = gtools[0].function_declarations
    assert len(decls) == 2
    names = {d.name for d in decls}
    assert names == {"read_file", "bash"}


def test_gemini_initial_messages(monkeypatch) -> None:  # noqa: ANN001
    _install_placeholder_keys(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "placeholder")
    from orchestrator_driver import make_backend
    backend = make_backend("gemini")
    msgs = backend.initial_messages("describe yourself")
    assert len(msgs) == 1
    assert msgs[0].role == "user"
    assert len(msgs[0].parts) == 1


def test_default_models_present() -> None:
    from orchestrator_driver import DEFAULT_MODELS
    assert "anthropic" in DEFAULT_MODELS
    assert "gemini" in DEFAULT_MODELS
    # Sanity: the model names look sensible.
    assert "claude" in DEFAULT_MODELS["anthropic"].lower()
    assert "gemini" in DEFAULT_MODELS["gemini"].lower()
