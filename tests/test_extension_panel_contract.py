"""Offline UI/observer fixtures for selected-tab mode; no live provider calls."""

import re
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "extensions" / "page-capture"


class IDs(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []

    def handle_starttag(self, tag, attrs):
        self.ids.extend(value for name, value in attrs if name == "id")


def test_sidepanel_markup_matches_packaged_script():
    parser = IDs()
    html = (EXTENSION / "sidepanel.html").read_text(encoding="utf-8")
    parser.feed(html)
    script = (EXTENSION / "sidepanel.js").read_text(encoding="utf-8")
    assert all(count == 1 for count in Counter(parser.ids).values())
    assert set(re.findall(r'byId\("([^"\n]+)"\)', script)) <= set(parser.ids)
    assert "innerHTML" not in script
    assert "agentic-panel-v1" in script and "agentic-panel-state-v1" in script
    assert "agent_visual_confirmed:false" in script
    assert 'send("status")' in script
    assert 'action("control", {action:name})' in script
    assert 'src="sidepanel.js"' in html and 'href="sidepanel.css"' in html
    assert 'role="alert"' in html and 'role="status"' in html
    assert "before saving" in html and "not screenshots" in html
    assert 'id="observation-diagnostics"' in html
    assert "report.observation_diagnostics" in script
    assert "current.reconnect_required === true" in script
    assert 'needsReconnect ? "Reconnect dashboard"' in script
    assert "live && !needsReconnect" in script
    assert "current.connection?.tab_id" in script
    assert "reconnect});" in script
    assert 'connection ? "Check connection"' in script
    assert 'window.addEventListener("pageshow", resumePolling)' in script
    assert 'document.addEventListener("visibilitychange"' in script
    assert "pollInFlight || !panelActive" in script
    assert "value.revision < (current.revision || 0)" in script
    assert 'operation === "status" ? 2:1' in script
    assert 'await action("status"); return;' in script
    assert "companion_reply_unknown" in script
    assert "current.website_activity?.observation" in script
    assert "async function requestReply(message, timeout)" in script
    assert 'operation === "status" ? 3000:12000' in script
    assert "Promise.race" in script


def test_executor_version_matches_manifest_and_does_not_reuse_an_old_cached_executor():
    import json

    manifest = json.loads((EXTENSION / "manifest.json").read_text(encoding="utf-8"))
    executor = (EXTENSION / "executor.js").read_text(encoding="utf-8")
    assert f"const version = '{manifest['version']}';" in executor
    assert "__agenticTabExecutor?.version === version" in executor


def test_packaged_observer_matches_shared_python_source_without_importing_it():
    source = (ROOT / "src/agentic_web_demo/browser_agent.py").read_text(encoding="utf-8")
    counter = re.search(r'COUNTER_OBSERVATION = r"""(.*?)"""', source, re.S).group(1)
    observer = re.search(r'AGENT_OBSERVATION = r"""(.*?)"""', source, re.S).group(1)
    packaged = (EXTENSION / "agent_observe.js").read_text(encoding="utf-8")
    assert f"globalThis.agenticInspectCounter = {counter};" in packaged
    assert "globalThis.agenticObserve = " + observer.replace(
        "__COUNTER_OBSERVATION__", "globalThis.agenticInspectCounter"
    ) + ";" in packaged


def test_dashboard_extension_review_never_submits_an_unbound_extension_plan():
    assets = ROOT / "src/agentic_web_demo/dashboard/static"
    script = (assets / "custom.js").read_text(encoding="utf-8")
    html = (assets / "index.html").read_text(encoding="utf-8")
    assert 'value="extension"' in html
    assert 'id="web-extension-agent-help"' in html
    assert 'event.data?.type !== "agentic-extension-review-v1"' in script
    assert "event.source !== window || event.origin !== location.origin" in script
    assert 'job.source === "extension"' in script
    assert 'if ($("web-source").value === "extension")' in script
