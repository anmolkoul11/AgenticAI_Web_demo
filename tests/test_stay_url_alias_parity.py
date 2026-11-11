"""Source contracts for normalized stay aliases; no browser/site/API calls."""

import re
from pathlib import Path

import pytest

from agentic_web_demo.stay_scope import URL_FIELDS


EXTENSION = Path(__file__).resolve().parents[1] / "extensions" / "page-capture"


@pytest.mark.parametrize("filename", ["worker.js", "executor.js"])
def test_selected_tab_allowlists_preserve_all_existing_normalized_stay_aliases(filename):
    source = (EXTENSION / filename).read_text(encoding="utf-8")
    match = re.search(r"const allowed = /(?P<pattern>.+)/i;", source)
    assert match is not None
    allowed = re.compile(match["pattern"], re.I)
    assert all(allowed.fullmatch(key) for key in URL_FIELDS)
    assert all(allowed.fullmatch(key.upper()) for key in URL_FIELDS)
    assert not any(allowed.fullmatch(key) for key in (
        "email", "password", "token", "return_url", "session", "arbitrary_query",
        "checkInDate", "adult_data", "room_count_private",
    ))
    compact = re.sub(r"\s+", "", source)
    assert "v.length<=128" in compact
    assert r"!/https?:|@|[\u0000-\u001f]/i.test(v)" in compact
    assert ".slice(0,12)" in compact
