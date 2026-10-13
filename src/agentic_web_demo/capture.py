"""Untrusted, user-reviewed page captures. No network fetches or browser credentials."""

from datetime import datetime
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agentic_web_demo.custom_fetch import public_url


def clean_url(value):
    parts = urlsplit(public_url(value))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


class Block(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^b[0-9]{1,4}$")
    kind: Literal["heading", "paragraph", "table_row", "link", "text"]
    text: str = Field(min_length=1, max_length=6000)
    href: str | None = Field(default=None, max_length=2048)
    # Optional for older extension captures and plain-text sources.
    group_id: str | None = Field(default=None, pattern=r"^g[0-9]{1,4}$")
    association: Literal["record", "page", "ambiguous"] | None = None
    heading_level: int | None = Field(default=None, ge=1, le=6)
    content_role: Literal["headline", "body", "other"] | None = None


class Coverage(BaseModel):
    """Bounded, untrusted collection diagnostics; never proof of full-site coverage."""

    model_config = ConfigDict(extra="forbid")
    collector_version: Literal["source-inventory-v1"]
    scope: Literal["loaded_dom"]
    eligible_text_chars: int = Field(ge=0, le=10_000_000)
    captured_text_chars: int = Field(ge=0, le=24_000)
    omitted_text_chars: int = Field(ge=0, le=10_000_000)
    excluded_navigation_chars: int = Field(ge=0, le=10_000_000)
    unique_links_detected: int = Field(ge=0, le=10_000)
    links_returned: int = Field(ge=0, le=100)
    candidate_limit_reached: bool
    frames_excluded: int = Field(ge=0, le=10_000)
    open_shadow_roots: int = Field(ge=0, le=20)
    record_groups: int = Field(ge=0, le=9999)
    limit_reasons: list[
        Literal[
            "element_scan_limit",
            "shadow_root_limit",
            "link_scan_limit",
            "inventory_link_limit",
            "text_scan_limit",
            "block_limit",
            "link_evidence_limit",
            "cell_text_limit",
            "text_budget",
        ]
    ] = Field(max_length=10)
    scroll_steps: int = Field(ge=0, le=8)
    at_page_end: bool
    content_settled: bool
    preparation: Literal["manual_snapshot", "bounded_browser"]


class Capture(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal[1]
    url: str = Field(max_length=2048)
    captured_at: datetime
    truncated: bool
    blocks: list[Block] = Field(min_length=1, max_length=600)
    coverage: Coverage | None = None

    @model_validator(mode="after")
    def bounded(self):
        self.url = clean_url(self.url)
        if self.captured_at.tzinfo is None:
            raise ValueError("Capture timestamp must include a timezone")
        if len({b.id for b in self.blocks}) != len(self.blocks):
            raise ValueError("Duplicate source block IDs")
        for block in self.blocks:
            if block.href:
                block.href = clean_url(block.href)
        size = sum(len(b.text) + len(b.href or "") for b in self.blocks)
        if not 80 <= size <= 24000:
            raise ValueError("Capture must contain 80-24,000 characters")
        if self.coverage is not None:
            if self.coverage.captured_text_chars != sum(len(b.text) for b in self.blocks):
                raise ValueError("Coverage character count does not match captured blocks")
            if self.coverage.links_returned > self.coverage.unique_links_detected:
                raise ValueError("Coverage link counts conflict")
            if self.coverage.limit_reasons or self.coverage.omitted_text_chars:
                self.truncated = True
        return self

    def page(self):
        blocks = [b.model_dump() for b in self.blocks]
        page = {
            "url": self.url,
            "text": "\n".join(b.text + ("\n" + b.href if b.href else "") for b in self.blocks),
            "blocks": blocks,
            "truncated": self.truncated,
        }
        if self.coverage is not None:
            page["coverage"] = self.coverage.model_dump()
        return page
