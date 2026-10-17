"""Structural source checks, never title guesses from URLs, summaries or approved links."""

import re
import unicodedata


def normalized(value):
    """Shared source-text normalization; preserve case and literal source facts."""
    return " ".join(unicodedata.normalize("NFC", str(value)).split())


def quote_in_block(quote, block):
    """A literal captured context is source evidence, not a model-inferred label."""
    quote = normalized(quote)
    context = block.get("value_context") or {}
    return bool(quote) and any(
        quote in normalized(text) for text in (
            block.get("text", "") + " " + (block.get("href") or ""),
            context.get("quote", ""),
        ) if text
    )


def article_content(content_type):
    """Field names alone must not turn a room/product description into article body."""
    return bool(re.search(
        r"(?:^|[\W_])(?:articles?|news|blogs?|stories|story|journalism)(?:$|[\W_])",
        content_type,
        re.I,
    ))


def is_body_field(field):
    """Unambiguous body names, not generic descriptions or index context."""
    return field in {
        "article_excerpt", "body", "body_excerpt", "body_text", "article_body",
        "story_body", "blog_body", "full_text", "full_content",
    }


def labelled_numeric_tokens(evidence, field):
    """Recover fused DOM labels without treating digits in names as source amounts."""
    words = set(field.lower().split("_"))
    price = bool(words.intersection({"price", "cost", "amount", "rate", "total"}))
    count = bool(words.intersection({"count", "reviews", "review_count", "quantity", "stock"}))
    rating = bool(words.intersection({"rating", "score"})) and not count
    labels = words - {"value", "displayed", "number", "minimum", "maximum", "min", "max"}
    if price:
        labels.update({"price", "cost", "amount", "rate", "total"})
    if rating:
        labels.update({"rating", "score", "scored"})
    if count and "review" in words:
        labels.update({"review", "reviews", "count"})
    labels.update(word + "s" for word in tuple(labels) if not word.endswith("s"))
    currencies = {"usd", "eur", "gbp", "cad", "aud", "jpy", "inr"}
    for match in re.finditer(r"[-+]?\d+(?:,\d{3})*(?:\.\d+)?", evidence):
        before, after = evidence[:match.start()], evidence[match.end():]
        # Never split a decimal/thousands token, version number or a signed value.
        if (before and before[-1] in "0123456789.,+-") or re.match(r"[.,]\d", after):
            continue
        left_match = re.search(r"([A-Za-z]+)$", before)
        right_match = re.match(r"([A-Za-z]+)", after)
        left = left_match.group(1).lower() if left_match else ""
        right = right_match.group(1).lower() if right_match else ""
        suffix = re.match(r"\s*(reviews?|ratings?|rooms?|adults?|items?|units?)\b", after, re.I)
        suffix = suffix.group(1).lower() if suffix else ""
        # Unknown fused names (Hotel31, X100) remain invalid even beside USD.
        left_allowed = not left or left in labels or (price and left in currencies)
        if count and suffix in {"review", "reviews"} and left == "score":
            left_allowed = True  # Legacy concatenation: 'score14,058 reviews'.
        right_allowed = not right or right in labels or (price and right in currencies)
        if price and re.match(r"(?:per\s*night|nightly)\b", after, re.I):
            right_allowed = True
        if count and right in {"review", "reviews", "items", "units"}:
            right_allowed = True
        if not left_allowed or not right_allowed:
            continue
        if rating and suffix in {"review", "reviews"}:
            continue
        labelled = left in labels or right in labels or (price and (left in currencies or right in currencies))
        if price and re.match(r"(?:per\s*night|nightly)\b", after, re.I):
            labelled = True
        if count and suffix in {"review", "reviews", "items", "units"}:
            labelled = True
        if labelled:
            yield match.group()


def multi_value_items(value, field):
    """Literal feature lists only; arbitrary prose/headlines are not split into facts."""
    if not re.search(
        r"(?:^|_)(?:amenit(?:y|ies)|facilit(?:y|ies)|features?|services?|attributes?)(?:_|$)",
        field,
    ):
        return []
    items = [normalized(item) for item in re.split(r"\s*[;|\n]\s*", str(value))]
    return items if 2 <= len(items) <= 16 and all(1 <= len(item) <= 200 for item in items) else []


def literal_list_item(item, quote):
    return bool(re.search(r"(?<!\w)" + re.escape(normalized(item)) + r"(?!\w)", normalized(quote)))


def list_group_supported(value, field, page, identity_groups):
    items = multi_value_items(value, field)
    return len(identity_groups) == 1 and all(
        any(
            literal_list_item(item, block["text"])
            and block.get("group_id") in identity_groups
            and block.get("association") != "ambiguous"
            for block in page.get("blocks", [])
        )
        for item in items
    )


def grouped_list_quote(evidence, value, field, page, identity_groups):
    """Replace joined quote fragments with an actual bounded contiguous source span."""
    items = multi_value_items(value, field)
    if not items or not list_group_supported(value, field, page, identity_groups):
        return None
    fragments = re.findall(r'["“]([^"”]+)["”]', evidence)
    if not 2 <= len(fragments) <= 16:
        return None
    # Accept only a quote-fragment notation, not arbitrary model prose around it.
    remainder = re.sub(r'["“][^"”]+["”]', "", evidence)
    if re.sub(r"[\s.;,|…-]", "", remainder):
        return None
    blocks = [
        block for block in page.get("blocks", [])
        if block.get("group_id") in identity_groups and block.get("association") != "ambiguous"
    ]
    if not all(any(normalized(part) in normalized(block["text"]) for block in blocks) for part in fragments):
        return None
    if not all(any(literal_list_item(item, part) for part in fragments) for item in items):
        return None
    source = normalized(page.get("text", ""))
    positions = []
    for part in fragments:
        part = normalized(part)
        matches = list(re.finditer(re.escape(part), source))
        if len(matches) != 1:
            return None
        positions.append((matches[0].start(), matches[0].end()))
    start, end = min(item[0] for item in positions), max(item[1] for item in positions)
    quote = source[start:end]
    if len(quote) > 2000:
        return None
    # All intervening captured content must stay in this same record container.
    if any(
        normalized(block["text"]) in quote and block.get("group_id") not in identity_groups
        for block in page.get("blocks", []) if normalized(block["text"])
    ):
        return None
    return quote


def is_headline_field(field, content_type):
    return field in {"article_title", "article_headline", "headline"} or (
        field in {"name", "record_name", "title", "heading", "story_title", "blog_title"}
        and article_content(content_type)
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
