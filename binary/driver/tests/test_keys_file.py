"""Tests for the keys.env loader.

The loader needs to:
  - Parse plain KEY=value lines, ignore comments and blanks.
  - Strip surrounding quotes but not interpret shell escapes.
  - Honor the search-path order (custom env var → cwd → home).
  - NEVER overwrite an existing environment variable.
  - Survive malformed lines without exploding.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

DRIVER_PARENT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DRIVER_PARENT))

import orchestrator_driver as drv  # noqa: E402


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def test_parse_env_file_basic() -> None:
    text = """
# comment line, ignored
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxx
GEMINI_API_KEY=AIzaSyABCDEFGHIJK
LLM_BACKEND=gemini

# another comment
"""
    out = drv._parse_env_file(text)
    assert out == {
        "ANTHROPIC_API_KEY": "sk-ant-xxxxxxxxxxxx",
        "GEMINI_API_KEY": "AIzaSyABCDEFGHIJK",
        "LLM_BACKEND": "gemini",
    }


def test_parse_env_file_strips_surrounding_quotes() -> None:
    text = '''
SINGLE='AIzaSyABC'
DOUBLE="sk-ant-XYZ"
NOQUOTE=plain-value
WITH_EQUALS_IN_VALUE=foo=bar=baz
'''
    out = drv._parse_env_file(text)
    assert out["SINGLE"] == "AIzaSyABC"
    assert out["DOUBLE"] == "sk-ant-XYZ"
    assert out["NOQUOTE"] == "plain-value"
    # Only the first `=` splits. The rest is value as-is.
    assert out["WITH_EQUALS_IN_VALUE"] == "foo=bar=baz"


def test_parse_env_file_ignores_malformed() -> None:
    text = """
GOOD=value
no_equals_sign_here
=empty_key_should_skip
GOOD2=value2
"""
    out = drv._parse_env_file(text)
    assert out == {"GOOD": "value", "GOOD2": "value2"}


def test_load_keys_from_file_via_custom_path(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    keyfile = tmp_path / "custom.env"
    _write(keyfile, "FROM_FILE=present\nLLM_BACKEND=gemini\n")
    monkeypatch.setenv("SWE_TEAM_KEYS", str(keyfile))
    # Make sure neither var is in env before loading.
    monkeypatch.delenv("FROM_FILE", raising=False)
    monkeypatch.delenv("LLM_BACKEND", raising=False)

    loaded = drv.load_keys_from_file()
    assert loaded == keyfile
    assert os.environ.get("FROM_FILE") == "present"
    assert os.environ.get("LLM_BACKEND") == "gemini"


def test_existing_env_var_wins_over_file(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    keyfile = tmp_path / "k.env"
    _write(keyfile, "GEMINI_API_KEY=from_file_value\n")
    monkeypatch.setenv("SWE_TEAM_KEYS", str(keyfile))
    monkeypatch.setenv("GEMINI_API_KEY", "from_shell_env")

    drv.load_keys_from_file()
    assert os.environ["GEMINI_API_KEY"] == "from_shell_env", \
        "file should NOT override existing env var"


def test_returns_none_when_no_file(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    # Point custom path at a non-existent location, isolate cwd / home
    # away from any real keys.env on the developer's machine.
    monkeypatch.setenv("SWE_TEAM_KEYS", str(tmp_path / "nope.env"))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path / "fake-home"))
    (tmp_path / "fake-home").mkdir()
    loaded = drv.load_keys_from_file()
    assert loaded is None


def test_loads_from_cwd_when_no_custom(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.delenv("SWE_TEAM_KEYS", raising=False)
    monkeypatch.delenv("FROM_CWD", raising=False)
    monkeypatch.chdir(tmp_path)
    _write(tmp_path / "keys.env", "FROM_CWD=yes\n")
    monkeypatch.setenv("HOME", str(tmp_path / "fake-home"))
    (tmp_path / "fake-home").mkdir()

    loaded = drv.load_keys_from_file()
    assert loaded == tmp_path / "keys.env"
    assert os.environ.get("FROM_CWD") == "yes"


def test_loads_from_home_xdg(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.delenv("SWE_TEAM_KEYS", raising=False)
    monkeypatch.delenv("FROM_HOME", raising=False)
    monkeypatch.chdir(tmp_path)  # no keys.env in cwd
    fake_home = tmp_path / "fake-home"
    target = fake_home / ".config" / "swe-team" / "keys.env"
    _write(target, "FROM_HOME=yes\n")
    monkeypatch.setenv("HOME", str(fake_home))

    loaded = drv.load_keys_from_file()
    assert loaded == target
    assert os.environ.get("FROM_HOME") == "yes"


def test_custom_path_wins_over_cwd(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.delenv("WHO_WON", raising=False)
    # Put one in cwd and one at a custom path; custom should win.
    monkeypatch.chdir(tmp_path)
    _write(tmp_path / "keys.env", "WHO_WON=cwd\n")
    custom = tmp_path / "elsewhere" / "k.env"
    _write(custom, "WHO_WON=custom\n")
    monkeypatch.setenv("SWE_TEAM_KEYS", str(custom))

    loaded = drv.load_keys_from_file()
    assert loaded == custom
    assert os.environ["WHO_WON"] == "custom"
