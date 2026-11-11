"""Desktop path/environment isolation; no backend, browser or network execution."""

from pathlib import Path

from agentic_web_demo import desktop


def test_default_desktop_data_is_per_user_and_not_inside_the_installation(tmp_path):
    local = tmp_path / "local-profile"
    assert desktop.user_data_dir({"LOCALAPPDATA": str(local)}) == local / "AgenticStudio" / "data"


def test_explicit_data_location_is_preserved(tmp_path):
    chosen = tmp_path / "existing-data"
    assert desktop.user_data_dir({"AGENTIC_DEMO_DATA_DIR": str(chosen)}) == chosen.resolve()


def test_frozen_resources_are_separate_from_user_data(monkeypatch, tmp_path):
    bundled = tmp_path / "installed" / "_internal"
    monkeypatch.setattr(desktop.sys, "_MEIPASS", str(bundled), raising=False)
    assert desktop.resource_root() == bundled
    data = desktop.user_data_dir({"LOCALAPPDATA": str(tmp_path / "profile")})
    assert bundled not in data.parents


def test_companion_setup_uses_the_folder_next_to_the_installed_executable(monkeypatch, tmp_path):
    executable = tmp_path / "installed" / "AgenticStudio.exe"
    monkeypatch.setattr(desktop.sys, "frozen", True, raising=False)
    monkeypatch.setattr(desktop.sys, "executable", str(executable))
    assert desktop.companion_dir() == executable.parent / "BrowserCompanion"


def test_desktop_setup_keeps_data_outside_bundle_and_does_not_require_demo_credentials(
    monkeypatch, tmp_path
):
    bundled = tmp_path / "readonly-resources"
    monkeypatch.setattr(desktop.sys, "_MEIPASS", str(bundled), raising=False)
    monkeypatch.delenv("AGENTIC_DEMO_DATA_DIR", raising=False)
    monkeypatch.delenv("DEMO_PASSWORD", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "profile"))
    monkeypatch.setenv("AGENTIC_DASHBOARD_DESKTOP", "0")
    monkeypatch.setenv("AGENTIC_DASHBOARD_POLICY_PATH", "old-path")
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", "0")
    # configure_environment mutates these values; monkeypatch restores all of them.
    monkeypatch.setenv("AGENTIC_DEMO_DATA_DIR", "")
    data = desktop.configure_environment()
    assert data.is_dir()
    assert desktop.os.environ["AGENTIC_DEMO_DATA_DIR"] == str(data)
    assert desktop.os.environ["AGENTIC_DASHBOARD_DESKTOP"] == "1"
    assert Path(desktop.os.environ["AGENTIC_DASHBOARD_POLICY_PATH"]) == bundled / "config/rules.yaml"
    assert desktop.os.environ["PLAYWRIGHT_BROWSERS_PATH"] == "0"
    assert "DEMO_PASSWORD" not in desktop.os.environ
    assert not bundled.exists()
