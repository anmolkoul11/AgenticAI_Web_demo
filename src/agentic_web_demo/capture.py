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


class Capture(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal[1]
    url: str = Field(max_length=2048)
    captured_at: datetime
    truncated: bool
    blocks: list[Block] = Field(min_length=1, max_length=200)

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
        return self

    def page(self):
        blocks = [b.model_dump() for b in self.blocks]
        return {
            "url": self.url,
            "text": "\n".join(b.text + ("\n" + b.href if b.href else "") for b in self.blocks),
            "blocks": blocks,
            "truncated": self.truncated,
        }
