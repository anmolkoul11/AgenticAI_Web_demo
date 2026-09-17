import json
from pathlib import Path

import pytest

from agentic_web_demo.cli import main
from agentic_web_demo.config import Settings


def test_default_settings():
    assert Settings.from_env({}) == Settings(Path("data"), "INFO")


def test_settings_override(tmp_path):
    settings = Settings.from_env(
        {
            "AGENTIC_DEMO_DATA_DIR": str(tmp_path / "records"),
            "AGENTIC_DEMO_LOG_LEVEL": "debug",
        }
    )
    assert settings == Settings(tmp_path / "records", "DEBUG")
    assert not settings.data_dir.exists()


@pytest.mark.parametrize("value", ["", "  "])
def test_empty_data_dir_is_rejected(value):
    with pytest.raises(ValueError, match="DATA_DIR"):
        Settings.from_env({"AGENTIC_DEMO_DATA_DIR": value})


def test_invalid_log_level_is_rejected():
    with pytest.raises(ValueError, match="LOG_LEVEL"):
        Settings.from_env({"AGENTIC_DEMO_LOG_LEVEL": "everything"})


def test_status_is_explicit_about_pending_live_verification(monkeypatch, capsys):
    monkeypatch.setenv("AGENTIC_DEMO_DATA_DIR", "./data")
    monkeypatch.setenv("AGENTIC_DEMO_LOG_LEVEL", "INFO")
    assert main(["status"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["checkpoint"] == "5c-reviewed-langgraph-acceptance-pending"
    assert result["reviewed_plan_execution_implemented"] is True
    assert result["workflow_implemented"] is True
    assert result["live_model_verified"] is False


def test_cli_reports_invalid_configuration(monkeypatch, capsys):
    monkeypatch.setenv("AGENTIC_DEMO_LOG_LEVEL", "invalid")
    with pytest.raises(SystemExit) as exc:
        main(["status"])
    assert exc.value.code == 2
    assert "LOG_LEVEL" in capsys.readouterr().err
