"""Small cleanup contracts: no browsers, provider calls or credential writes."""

import tomllib
from pathlib import Path

import pytest

from agentic_web_demo import (
    browser_runtime,
    browser_task,
    custom_extract,
    enrichment,
    source_fields,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Cafe\u0301\n  Premier\tLeague", "Café Premier League"),
        ("  Hotel\u00a0Boston  ", "Hotel Boston"),
        ("Football", "Football"),
        ("football", "football"),
        (150, "150"),
    ],
)
def test_source_normalization_is_shared_and_case_preserving(value, expected):
    assert custom_extract.normalized is source_fields.normalized
    assert enrichment.normalized is source_fields.normalized
    assert source_fields.normalized(value) == expected


def test_task_and_runtime_share_control_flattening_without_copying_controls():
    first = {"id": "0:1", "value": "Boston"}
    second = {"id": "1:1", "value": "3"}
    observation = {"frames": [{"controls": [first]}, {}, {"controls": [second]}]}
    assert browser_task.controls is browser_runtime.controls
    flattened = browser_task.controls(observation)
    assert flattened == [first, second]
    assert flattened[0] is first
    assert flattened[1] is second
    assert browser_task.controls({}) == []


def test_generated_extension_collector_matches_canonical_packaged_collector():
    canonical = ROOT / "src/agentic_web_demo/dashboard/static/capture_dom.js"
    generated = ROOT / "extensions/page-capture/capture_dom.js"
    assert canonical.read_bytes() == generated.read_bytes(), (
        "Collector copies drifted. Edit the dashboard/static canonical collector, then "
        "run uv run --locked python scripts/sync_capture.py --write and review the diff."
    )


def test_httpx_remains_a_runtime_dependency_without_duplicate_dev_declaration():
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    assert "httpx>=0.28,<1" in metadata["project"]["dependencies"]
    assert not any(item.startswith("httpx") for item in metadata["dependency-groups"]["dev"])
    package = next(item for item in lock["package"] if item["name"] == "agenticai-web-demo")
    assert any(item["name"] == "httpx" for item in package["dependencies"])
    assert not any(item["name"] == "httpx" for item in package["dev-dependencies"]["dev"])
