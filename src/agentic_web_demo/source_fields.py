"""Structural source checks, never title guesses from URLs, summaries or approved links."""

import re
import unicodedata


def normalized(value):
    """Shared source-text normalization; preserve case and literal source facts."""
    return " ".join(unicodedata.normalize("NFC", str(value)).split())


def is_headline_field(field, content_type):
    return field in {"article_title", "article_headline", "headline"} or (
        field in {"title", "heading", "story_title", "blog_title"}
        and bool(re.search(r"article|news|blog|stor", content_type, re.I))
    )


def primary_headline(page):
    blocks = [
        block
        for block in page.get("blocks", [])
        if block.get("kind") == "heading"
        and (block.get("heading_level") == 1 or block.get("content_role") == "headline")
        and block.get("association") != "ambiguous"
    ]
    distinct = {normalized(block["text"]): block for block in blocks}
    return next(iter(distinct.values())) if len(distinct) == 1 else None


def linked_headline(page, url):
    """One literal heading bound to the declared link, not its teaser/kicker."""
    blocks = page.get("blocks", [])
    groups = {
        block["group_id"] for block in blocks if block.get("href") == url and block.get("group_id")
    }
    headings = [
        block
        for block in blocks
        if block.get("kind") == "heading"
        and block.get("association") != "ambiguous"
        and (block.get("href") == url or block.get("group_id") in groups)
    ]
    distinct = {normalized(block["text"]): block for block in headings}
    return next(iter(distinct.values())) if len(distinct) == 1 else None


def headline_issue(value, page):
    """Structured capture proves a field role; plain pasted text cannot prove DOM roles."""
    blocks = page.get("blocks", [])
    if not blocks:
        return None
    primary = primary_headline(page)
    if primary and page.get("source_kind") == "detail":
        return None if normalized(value) == normalized(primary["text"]) else "not_primary_headline"
    if page.get("source_kind") == "detail":
        # Old captures lack levels. Accept an exact legacy heading, never a paragraph.
        headings = [
            b
            for b in blocks
            if b.get("kind") == "heading"
            and b.get("heading_level") is None
            and b.get("content_role") is None
        ]
        if any(normalized(value) == normalized(b["text"]) for b in headings):
            return None
        return "primary_headline_not_captured"
    matching = [
        block
        for block in blocks
        if block.get("kind") == "link" and normalized(value) == normalized(block["text"])
    ]
    if matching and all(
        block.get("href")
        and linked_headline(page, block["href"])
        and normalized(value) != normalized(linked_headline(page, block["href"])["text"])
        for block in matching
    ):
        return "kicker_not_linked_headline"
    return (
        None
        if any(
            b.get("kind") in {"heading", "link"} and normalized(value) == normalized(b["text"])
            for b in blocks
        )
        else "title_not_supported_by_heading_or_link"
    )


def excerpt_issue(quote, page):
    blocks = page.get("blocks", [])
    if not blocks:
        return None
    if page.get("source_kind") == "index":
        return "detail_body_not_captured"
    return (
        None
        if any(
            b.get("kind") == "paragraph"
            and b.get("content_role") in {None, "body"}
            and normalized(quote) in normalized(b["text"])
            for b in blocks
        )
        else "excerpt_not_supported_by_body_paragraph"
    )
