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


def article_priority_terms(instructions):
    """Literal topic cues order article sources; they never decide relevance."""
    if not re.search(r"\b(?:articles?|headlines?|news|stories)\b", instructions, re.I):
        return []
    topic = re.search(
        r"\b(?:related\s+to|about|concerning|regarding)\s+([^.!?\n]+)", instructions, re.I
    )
    text = topic.group(1) if topic else instructions
    ignored = {
        "find", "get", "give", "show", "fetch", "collect", "extract", "please", "articles",
        "article", "headlines", "headline", "news", "stories", "story", "related", "about",
        "from", "with", "this", "that", "these", "those", "the", "and", "for", "all",
        "current", "page", "website", "site", "only", "results", "links", "include",
    }
    return list(dict.fromkeys(
        word for word in re.findall(r"[a-z]{3,32}", text.casefold()) if word not in ignored
    ))[:12]


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


def _linked_headings(page, url):
    blocks = page.get("blocks", [])
    groups = {
        block["group_id"] for block in blocks if block.get("href") == url and block.get("group_id")
    }
    return [
        block
        for block in blocks
        if block.get("kind") == "heading"
        and block.get("association") != "ambiguous"
        and (block.get("href") == url or block.get("group_id") in groups)
    ]


def linked_headline(page, url):
    """One literal heading bound to the declared link, not its teaser/kicker."""
    distinct = {normalized(block["text"]): block for block in _linked_headings(page, url)}
    return next(iter(distinct.values())) if len(distinct) == 1 else None


def ambiguous_linked_headline(page, url):
    """Multiple distinct linked headings require a source-role choice, not a rank guess."""
    return len({normalized(block["text"]) for block in _linked_headings(page, url)}) > 1


def selected_record_headline(row, page, urls):
    """Validate a model's source-role choice; never infer a role from heading size/order.

    This proves which literal source block the model selected and its record
    association. It does not prove the model interpreted that block's role correctly.
    Returned reason codes can be attached to the caller's actual identity field.
    """
    selected_id = getattr(row, "headline_block_id", None)
    label_ids = getattr(row, "label_block_ids", []) or []
    if not selected_id:
        return None, ["headline_selection_missing"] if label_ids else []
    blocks = page.get("blocks", [])
    matching = [block for block in blocks if block.get("id") == selected_id]
    if len(matching) != 1:
        return None, ["headline_selection_not_captured"]
    selected = matching[0]
    if selected.get("kind") not in {"heading", "link"} or not normalized(selected.get("text", "")):
        return None, ["headline_selection_not_heading_or_link"]
    declared_urls = {url for url in urls if url}
    primary = primary_headline(page)
    native_primary = bool(
        primary is selected and declared_urls
        and declared_urls <= {page.get("url"), page.get("requested_url")}
        and (page.get("source_kind") == "detail" or page.get("source_kind") != "index"
             and selected.get("content_role") == "headline")
    )
    if selected.get("association") in {"ambiguous", "page"} and not native_primary:
        return None, ["headline_selection_not_record_bound"]
    group = selected.get("group_id")
    href = selected.get("href")
    if not group and not href and not native_primary:
        return None, ["headline_selection_not_record_bound"]
    if len(declared_urls) > 1 and not native_primary:
        return None, ["headline_selection_url_ambiguous"]
    if declared_urls and not native_primary:
        declared = next(iter(declared_urls))
        group_bound = group and any(
            block.get("group_id") == group and block.get("href") == declared
            and block.get("association") not in {"ambiguous", "page"} for block in blocks
        )
        if href and href != declared or not href and not group_bound:
            return None, ["headline_selection_url_mismatch"]
    binding_href = href or (page.get("url") if native_primary else None)
    issues = []
    for label_id in dict.fromkeys(label_ids):
        matches = [block for block in blocks if block.get("id") == label_id]
        if len(matches) != 1:
            issues.append("headline_label_not_captured")
            continue
        label = matches[0]
        if label_id == selected_id or normalized(label.get("text", "")) == normalized(selected["text"]):
            issues.append("headline_selection_is_label")
        if (label.get("association") in {"ambiguous", "page"}
                or (label.get("group_id") != group if group else
                    bool(label.get("group_id")) or label.get("href") != binding_href)):
            issues.append("headline_label_cross_record")
    return (None if issues else selected), list(dict.fromkeys(issues))


def headline_issue(value, page):
    """Structured capture proves a field role; plain pasted text cannot prove DOM roles."""
    blocks = page.get("blocks", [])
    if not blocks:
        return None
    primary = primary_headline(page)
    if primary and (
        page.get("source_kind") == "detail"
        or page.get("source_kind") != "index" and primary.get("content_role") == "headline"
    ):
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


def article_record_issue(value, page):
    """Reject captured non-article affordances without guessing titles from URLs.

    Literal headline links remain valid evidence. Topic relevance alone cannot
    turn a game launcher, navigation link or coverage landing page into a story.
    """
    title = normalized(value) if value is not None else ""
    if not title:
        return "article_headline_missing"
    blocks = page.get("blocks", [])
    matches = [block for block in blocks
               if block.get("kind") in {"heading", "link"}
               and block.get("association") != "ambiguous"
               and normalized(block.get("text", "")) == title]
    if blocks and not matches:
        return "article_headline_not_captured"
    # These are game-launch instructions, not every headline containing 'game'.
    if re.fullmatch(
        r"^(?:play|solve|try)\s+(?:(?:our|the|today['’]s|daily)\s+)?"
        r"(?:connections(?:\s*:\s*[\w -]{1,40}\s+edition)?|wordle|sudoku|crosswords?|"
        r"(?:sports\s+)?(?:puzzles?|quizzes?|quiz|games?))"
        r"(?:\s+(?:now|today|for free))?[.!]?",
        title, re.I,
    ):
        return "non_article_game"
    if page.get("source_kind") != "index" and any(
        block.get("kind") == "heading" and block.get("content_role") == "headline"
        for block in matches
    ):
        return None
    if matches and all(block.get("association") == "page" for block in matches):
        return "non_article_navigation"
    section = (
        r"(?:sports|news|world|politics|business|technology|science|health|culture|opinion)"
    )
    browse_label = bool(re.fullmatch(
        section + r"\s+(?:coverage|section)", title, re.I,
    )) or bool(re.fullmatch(
        r"(?:see|view|browse|explore|more|all|latest)\s+(?:all\s+)?"
        + section + r"(?:\s+(?:coverage|news|headlines|section|stories))?",
        title, re.I,
    ))
    if browse_label:
        return "non_article_section"
    return None


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
