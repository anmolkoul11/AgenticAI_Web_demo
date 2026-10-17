"""Untrusted, user-reviewed page captures. No network fetches or browser credentials."""

import re
from datetime import datetime
from typing import Literal
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agentic_web_demo.custom_fetch import public_url

# Capture identity, not navigation state: omit attribution/session/redirect data,
# but retain bounded query-addressed records (for example /article?id=123).
# Keep this definition aligned with capture_dom.js. Actual browser navigation
# continues to use the live, reviewed link rather than this evidence URL.
_IDENTITY_QUERY = re.compile(
    r"^(?:id|item|product|article|story|hotel|listing|slug|variant|page|p|"
    r"(?:item|product|article|story|hotel|listing|variant)_id)$",
    re.IGNORECASE,
)
_GENERIC_QUERY_PATH = re.compile(
    r"(?:^|/)(?:index|view|detail|details|item|product|article|story|hotel|listing)"
    r"(?:\.(?:php|aspx?|html?))?/?$",
    re.IGNORECASE,
)
_NON_IDENTITY_QUERY = re.compile(
    r"^utm_|^(?:aid|sid|label|lang|ref|source|campaign|affiliate|clickid|gclid|fbclid)$",
    re.IGNORECASE,
)


def query_identity_omitted(value):
    """An omitted identity component cannot become a guessed canonical URL."""
    parts = urlsplit(public_url(value))
    pairs = parse_qsl(parts.query, keep_blank_values=True)
    retained = parse_qsl(urlsplit(clean_url(value)).query, keep_blank_values=True)
    # Losing one meaningful component is ambiguous even if a small variant/page
    # query survives. Otherwise two oversized IDs could merge into one record.
    pending = list(retained)
    for pair in pairs:
        if _IDENTITY_QUERY.fullmatch(pair[0]):
            if pair not in pending:
                return True
            pending.remove(pair)
    if parts.path not in ("", "/") and not _GENERIC_QUERY_PATH.search(parts.path):
        return False
    # Unknown parameters on a generic endpoint may be the actual record key,
    # including security-sensitive keys we deliberately do not preserve.
    return any(
        not _IDENTITY_QUERY.fullmatch(key) and not _NON_IDENTITY_QUERY.search(key)
        for key, _ in pairs
    )


def clean_url(value):
    parts = urlsplit(public_url(value))
    pairs = []
    query_size = 0
    for key, content in parse_qsl(parts.query, keep_blank_values=True):
        if not _IDENTITY_QUERY.fullmatch(key) or len(content) > 128:
            continue
        # URL-valued queries, control characters and email-like values are not
        # necessary to identify source records and can carry account information.
        if "://" in content or "@" in content or any(ord(c) < 32 for c in content):
            continue
        encoded = urlencode([(key, content)])
        if len(pairs) >= 8 or query_size + len(encoded) + bool(pairs) > 512:
            continue
        query_size += len(encoded) + bool(pairs)
        pairs.append((key, content))
    path = quote(parts.path, safe="/%:@!$&'()*+,;=-._~[]")
    return public_url(urlunsplit((parts.scheme, parts.netloc, path, urlencode(pairs), "")))


class ValueContext(BaseModel):
    """Literal, record-local amount relationships; not an inferred price role."""

    model_config = ConfigDict(extra="forbid")
    quote: str = Field(min_length=1, max_length=500)
    label: str = Field(default="", max_length=160)
    relation: Literal["local_container"]
    struck_through: bool


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
    content_role: Literal["headline", "body", "other", "currency_setting"] | None = None
    value_context: ValueContext | None = None

    @model_validator(mode="after")
    def literal_value_context(self):
        if self.value_context is not None:
            context = self.value_context
            def tidy(value):
                return " ".join(value.split())

            if (
                self.association != "record" or self.group_id is None
                or len(self.text) > 240
                or tidy(self.text) not in tidy(context.quote)
                or (context.label and tidy(context.label) not in tidy(context.quote))
            ):
                raise ValueError("Value context must quote its literal record-local value and label")
        return self


class Coverage(BaseModel):
    """Bounded, untrusted collection diagnostics; never proof of full-site coverage."""

    model_config = ConfigDict(extra="forbid")
    collector_version: Literal[
        "source-inventory-v1", "source-inventory-v2", "source-inventory-v3", "source-inventory-v4",
        "source-inventory-v5", "source-inventory-v6",
    ]
    scope: Literal["loaded_dom"]
    page_url_identity_omitted: bool = False
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
            "record_bundle_limit",
            "url_identity_omitted",
            "value_context_limit",
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
        page_identity_omitted = query_identity_omitted(self.url)
        self.url = clean_url(self.url)
        if self.coverage is not None and page_identity_omitted:
            self.coverage.page_url_identity_omitted = True
            if "url_identity_omitted" not in self.coverage.limit_reasons and (
                len(self.coverage.limit_reasons) < 10
            ):
                self.coverage.limit_reasons.append("url_identity_omitted")
        if page_identity_omitted or (
            self.coverage is not None and self.coverage.page_url_identity_omitted
        ):
            self.truncated = True
        if self.captured_at.tzinfo is None:
            raise ValueError("Capture timestamp must include a timezone")
        if len({b.id for b in self.blocks}) != len(self.blocks):
            raise ValueError("Duplicate source block IDs")
        if sum(
            len(b.value_context.quote) + len(b.value_context.label)
            for b in self.blocks if b.value_context is not None
        ) > 6000:
            raise ValueError("Value relationship metadata exceeds 6,000 characters")
        for block in self.blocks:
            if block.href:
                if query_identity_omitted(block.href):
                    block.href = None
                    block.association = "ambiguous"
                    block.value_context = None
                    if self.coverage is not None:
                        reasons = self.coverage.limit_reasons
                        if "url_identity_omitted" not in reasons and len(reasons) < 10:
                            reasons.append("url_identity_omitted")
                    self.truncated = True
                else:
                    block.href = clean_url(block.href)
        source_size = sum(len(b.text) + len(b.href or "") for b in self.blocks)
        context_size = sum(
            len(b.value_context.quote) + len(b.value_context.label)
            for b in self.blocks if b.value_context is not None
        )
        if source_size < 80 or source_size + context_size > 24000:
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
        text = "\n".join(b.text + ("\n" + b.href if b.href else "") for b in self.blocks)
        # Context is a literal rendered span, not a synthesized label/value join.
        # Retain it as source evidence when its inline relationship was split
        # into separate scalar blocks. Repeated/self-contained quotes add no text.
        for block in self.blocks:
            if block.value_context and block.value_context.quote not in text:
                text += "\n" + block.value_context.quote
        page = {
            "url": self.url,
            "text": text,
            "blocks": blocks,
            "truncated": self.truncated,
        }
        if self.coverage is not None:
            page["coverage"] = self.coverage.model_dump()
        return page
