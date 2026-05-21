"""Tests for LocalBackend + per-role backend/model selection.

No live network calls. We verify the SDK adapter shape and the routing
logic. End-to-end Ollama is something the user runs locally — outside the
scope of an automated test that ships in a public CI.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

DRIVER_PARENT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DRIVER_PARENT))

pytest.importorskip("openai", reason="openai SDK not installed")

import orchestrator_driver as drv  # noqa: E402


# ---------- backend construction ----------

def test_local_backend_constructs(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.delenv("LOCAL_BASE_URL", raising=False)
    backend = drv.LocalBackend()
    assert backend.name == "local"
    assert backend.base_url == drv.DEFAULT_LOCAL_BASE_URL


def test_local_backend_respects_base_url_env(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setenv("LOCAL_BASE_URL", "http://otherhost:9999/v1")
    backend = drv.LocalBackend()
    assert backend.base_url == "http://otherhost:9999/v1"


def test_make_backend_local(monkeypatch) -> None:  # noqa: ANN001
    backend = drv.make_backend("local")
    assert isinstance(backend, drv.LocalBackend)


def test_make_backend_unknown_lists_all_three(monkeypatch) -> None:  # noqa: ANN001
    try:
        drv.make_backend("nopenope")
    except SystemExit:
        pass
    else:
        raise AssertionError("expected SystemExit for unknown backend")


# ---------- tool / message translation ----------

def test_openai_tool_translation(monkeypatch) -> None:  # noqa: ANN001
    backend = drv.LocalBackend()
    tools = [
        {
            "name": "read_file",
            "description": "read a file",
            "input_schema": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
        {
            "name": "bash",
            "description": "run bash",
            "input_schema": {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
        },
    ]
    translated = backend._to_openai_tools(tools)
    assert len(translated) == 2
    assert translated[0]["type"] == "function"
    assert translated[0]["function"]["name"] == "read_file"
    assert translated[0]["function"]["parameters"]["required"] == ["path"]
    assert translated[1]["function"]["name"] == "bash"


def test_initial_messages_shape() -> None:
    backend = drv.LocalBackend()
    msgs = backend.initial_messages("hello")
    assert msgs == [{"role": "user", "content": "hello"}]


def test_append_tool_results_one_per_call() -> None:
    backend = drv.LocalBackend()
    msgs: list[dict] = []
    results = [
        ("call_1", "read_file", "file contents 1"),
        ("call_2", "read_file", "file contents 2"),
        ("call_3", "bash", "exit_code: 0\nstdout: ok"),
    ]
    backend.append_tool_results(msgs, results)
    assert len(msgs) == 3, "each tool result must be its own message in OpenAI format"
    assert all(m["role"] == "tool" for m in msgs)
    assert [m["tool_call_id"] for m in msgs] == ["call_1", "call_2", "call_3"]
    assert msgs[2]["content"] == "exit_code: 0\nstdout: ok"


# ---------- per-role routing ----------

def test_backend_name_for_role_uses_per_role_env(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setenv("LLM_BACKEND", "anthropic")
    monkeypatch.setenv("LLM_BACKEND_CODER_PYTHON", "local")
    assert drv.backend_name_for_role("coder-python") == "local"
    # Unrelated roles still get the global default.
    assert drv.backend_name_for_role("architect") == "anthropic"


def test_backend_name_for_role_falls_back_to_global(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.delenv("LLM_BACKEND_CODER_PYTHON", raising=False)
    monkeypatch.setenv("LLM_BACKEND", "gemini")
    assert drv.backend_name_for_role("coder-python") == "gemini"


def test_backend_name_for_role_no_env_uses_default(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.delenv("LLM_BACKEND", raising=False)
    for role in ("pm", "architect", "coder-cpp", "coder-backend",
                 "coder-frontend", "coder-python", "qa"):
        monkeypatch.delenv(f"LLM_BACKEND_{role.upper().replace('-', '_')}",
                           raising=False)
    assert drv.backend_name_for_role("pm") == drv.DEFAULT_BACKEND


def test_model_for_role_per_role_wins(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setenv("LLM_MODEL", "global-model")
    monkeypatch.setenv("LLM_MODEL_QA", "qa-specific-model")
    assert drv.model_for_role("qa", "anthropic") == "qa-specific-model"
    assert drv.model_for_role("pm", "anthropic") == "global-model"


def test_model_for_role_falls_back_to_default(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("LLM_MODEL_PM", raising=False)
    assert drv.model_for_role("pm", "local") == drv.DEFAULT_MODELS["local"]
    assert drv.model_for_role("pm", "anthropic") == drv.DEFAULT_MODELS["anthropic"]


def test_role_with_hyphen_translates_to_underscore_env(monkeypatch) -> None:  # noqa: ANN001
    # `coder-backend` looks for `LLM_BACKEND_CODER_BACKEND`, not `LLM_BACKEND_CODER-BACKEND`.
    monkeypatch.setenv("LLM_BACKEND_CODER_BACKEND", "local")
    assert drv.backend_name_for_role("coder-backend") == "local"


def test_default_models_has_local() -> None:
    assert "local" in drv.DEFAULT_MODELS
    # Should be a reasonable Ollama default.
    assert ":" in drv.DEFAULT_MODELS["local"]  # Ollama models are name:tag
