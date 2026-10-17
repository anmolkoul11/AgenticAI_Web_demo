"""Local display groups and bounded, source-bound completeness observations.

These helpers never infer facts, fill model cells, fetch pages or call a model.
Unmapped source wording is useful context, not a verified answer to a null field.
"""

import re
from copy import deepcopy

from agentic_web_demo.record_identity import identity_field
from agentic_web_demo.source_fields import normalized, quote_in_block


_FAMILIES = (
    ("pricing", "Prices & charges", r"prices?|costs?|amounts?|currency|tax(?:es)?|fees?|discounts?|nightly|rates?"),
    ("feedback", "Ratings & feedback", r"ratings?|scores?|reviews?|feedback"),
    ("location", "Location", r"location|address|city|country|region|destination|distance|latitude|longitude"),
    ("features", "Features & services", r"amenity|amenities|facility|facilities|features?|services?|attributes?|accessibility"),
    ("terms", "Terms & availability", r"cancellation|refund|payment|pay|breakfast|meal|warranty|return|availability|stock|policy|policies"),
    ("configuration", "Options & configuration", r"rooms?|beds?|occupancy|adults?|child|children|capacity|sizes?|materials?|colou?rs?|variants?|configuration"),
    ("timing", "Dates & times", r"date|time|published|updated|duration|check_in|check_out|schedule"),
    ("source", "Links & source", r"url|link|source|author|publisher|byline"),
    ("overview", "Overview", r"name|title|headline|description|snippet|excerpt|context|summary|overview|body|content"),
)
_SECTION_ORDER = ("overview", "pricing", "location", "configuration", "features", "terms", "feedback", "timing", "details", "source")
_DETAIL_LABELS = {family: label for family, label, _ in _FAMILIES} | {
    "terms": "Terms & inclusions", "promotions": "Offers & recommendations",
    "details": "Other source details",
}
_DETAIL_ORDER = (*_SECTION_ORDER[:6], "promotions", *_SECTION_ORDER[6:])
_WINDOW_SUFFIX = re.compile(r"\s+opens? in (?:a )?new (?:window|tab)\s*$", re.I)
# Labels only organize literal quotes; these expressions never supply a value,
# rating scale, availability claim or feature missing from the model's output.
_DETAIL_HINTS = (
    ("feedback", r"^(?:(?:location|cleanliness|comfort|staff|facilities|value(?: for money)?)\s*:?\s*\d+(?:\.\d+)?(?:\s*/\s*\d+(?:\.\d+)?)?$|(?:scored|rated)\s*\d)"),
    ("promotions", r"\b(?:recommended|recommendation|featured|deals?|offers?|promotions?)\b"),
    ("configuration", r"\b\d+\s+nights?\b"),
    ("pricing", r"\bper\s+night\b"),
    ("features", r"\b(?:wi[ -]?fi|swimming pool|parking|wheelchair accessible)\b"),
)
_NOISE = re.compile(
    r"^(?:opens? in (?:a )?new (?:window|tab)|see availability|show on map|read more|"
    r"view details|learn more|book now|reserve|search|share|save|\d+\s*[×x]?)$",
    re.I,
)
_STOP_WORDS = {"a", "an", "the", "at", "for", "of", "in", "to", "on", "by", "with", "from", "is", "are", "your", "our"}
_MAX_DETAILS = 10
_MAX_TEXT = 320


def _column(column, name):
    return column.get(name, "") if isinstance(column, dict) else getattr(column, name, "")


def field_family(column):
    """Organize existing fields by wording; an unfamiliar field stays in Details."""
    name = _column(column, "name").lower()
    # Names are stronger than free-form descriptions (for example review_count
    # described as 'total reviews' is feedback, not a monetary total).
    for text in (name, _column(column, "description").lower()):
        for family, _, words in _FAMILIES:
            if re.search(r"(?:^|[\W_])(?:" + words + r")(?:$|[\W_])", text):
                return family
    return "details"


def group_output_fields(columns):
    labels = {family: label for family, label, _ in _FAMILIES} | {"details": "Details"}
    groups = {}
    for column in columns:
        groups.setdefault(field_family(column), []).append(_column(column, "name"))
    return [
        {"id": family, "label": labels[family], "fields": groups[family]}
        for family in _SECTION_ORDER if family in groups
    ]


def presentation_contract(columns):
    """Display the existing schema's units and explanations, never guessed ones."""
    return {
        "sections": group_output_fields(columns),
        "field_metadata": {
            _column(column, "name"): {
                key: _column(column, key) for key in ("unit", "description", "kind")
            }
            for column in columns
        },
    }


def _page_groups(row, pages, columns):
    """Only one identity-bound record group per actually cited source page.

    A linked page participates only when a returned field cites that page and
    that quote belongs to the same uniquely identified record group. A shared
    title, page-level currency, duplicate page URL or neighboring group cannot
    silently become additional evidence for the record.
    """
    names = [_column(column, "name") for column in columns]
    identity = identity_field(names) if names else None
    value = row.get(identity)
    quote = row.get("evidence", {}).get(identity)
    if not value or not quote or not re.search(r"(?:^|_)(?:name|title|headline|heading)(?:_|$)", identity):
        return []
    sources = row.get("evidence_sources", {})
    identity_url = (sources.get(identity) or {}).get("source_url", row.get("source_url"))
    urls = {identity_url} | {
        info.get("source_url") for field, info in sources.items()
        if row.get(field) not in (None, "") and row.get("evidence", {}).get(field)
    }
    result = []
    for url in urls - {None}:
        matching_pages = [page for page in pages if page.get("url") == url]
        if len(matching_pages) != 1:
            continue
        page = matching_pages[0]
        blocks = [block for block in page.get("blocks", []) if block.get("association") not in {"page", "ambiguous"}]
        groups = {
            block["group_id"] for block in blocks
            if block.get("group_id") and block.get("kind") in {"heading", "link", "table_row"}
            and normalized(value) == normalized(block.get("text", ""))
            and (url != identity_url or quote_in_block(quote, block))
        }
        if len(groups) != 1:
            continue
        group = [block for block in blocks if block.get("group_id") in groups]
        if url != identity_url and not any(
            row.get(field) not in (None, "") and info.get("source_url") == url
            and any(quote_in_block(row.get("evidence", {}).get(field, ""), block) for block in group)
            for field, info in sources.items()
        ):
            continue
        result.append((page, group))
    return sorted(result, key=lambda item: item[0]["url"])


def _covered(text, row, page_url):
    """A short quote must not hide the rest of a larger source block."""
    text = normalized(text)
    for field, quote in row.get("evidence", {}).items():
        if row.get(field) in (None, ""):
            continue
        source = (row.get("evidence_sources", {}).get(field) or {}).get("source_url", row.get("source_url"))
        if source == page_url and (
            re.search(r"(?<!\w)" + re.escape(text) + r"(?!\w)", normalized(quote))
            or re.search(r"(?<!\w)" + re.escape(text) + r"(?!\w)", normalized(row[field]))
        ):
            return True
    return False


def _identity_window_duplicate(text, row, columns):
    """Ignore navigation suffixes only on an otherwise identical identity.

    This does not relax record-container binding or shorten substantive titles.
    The original block remains available in source evidence.
    """
    names = [_column(column, "name") for column in columns]
    identity = identity_field(names) if names else None
    if not identity or not row.get(identity) or not row.get("evidence", {}).get(identity):
        return False
    return bool(_WINDOW_SUFFIX.search(text)) and normalized(_WINDOW_SUFFIX.sub("", text)) == normalized(row[identity])


def group_source_details(details):
    """Group bounded source wording for display, without mapping output fields."""
    groups = {}
    for item in details:
        text = item["text"]
        family = next((family for family, pattern in _DETAIL_HINTS if re.search(pattern, text, re.I)), None)
        if family is None:
            family = field_family({"name": text})
        groups.setdefault(family, []).append(item)
    return [
        {"id": family, "label": _DETAIL_LABELS[family], "details": groups[family]}
        for family in _DETAIL_ORDER if family in groups
    ]


def _phrase(value):
    return " ".join(word for word in re.findall(r"[^\W_]+", str(value).casefold()) if word not in _STOP_WORDS)


def _related(column, text):
    source = _phrase(text)
    for wording in (_column(column, "name"), _column(column, "description")):
        phrase = _phrase(wording)
        # One generic token such as 'features' or 'value' is not a safe relation.
        if 2 <= len(phrase.split()) <= 6 and re.search(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", source):
            return True
    return False


def annotate_source_coverage(rows, pages, columns):
    """Deep-copy rows and retain compact overlooked source wording, not guesses.

    ``related_fields`` means matching wording was captured, never that a missing
    boolean is true. Negations and qualifiers are retained verbatim. Coverage is
    bounded to captured, uniquely bound record containers, not the whole site.
    """
    result = deepcopy(rows)
    names = [_column(column, "name") for column in columns]
    for row in result:
        missing = [name for name in names if row.get(name) in (None, "")]
        details, seen, oversized = [], {}, 0
        groups = _page_groups(row, pages, columns)
        for page, blocks in groups:
            for block in blocks:
                text = normalized(block.get("text", ""))
                if not text or _NOISE.fullmatch(text) or re.match(r"https?://", text) or _covered(text, row, page["url"]) or _identity_window_duplicate(text, row, columns):
                    continue
                # Body paragraphs stay with their existing content fields; do
                # not copy long article bodies into a feature/details drawer.
                if len(text) > _MAX_TEXT:
                    oversized += 1
                    continue
                key = (page["url"], text.casefold())
                if key in seen:
                    if block.get("id") and block["id"] not in seen[key]["block_ids"]:
                        seen[key]["block_ids"].append(block["id"])
                    continue
                item = {"text": text, "source_url": page["url"], "block_ids": [block["id"]] if block.get("id") else []}
                seen[key] = item
                details.append(item)
        retained = details[:_MAX_DETAILS]
        related = {
            _column(column, "name"): [item for item in retained if _related(column, item["text"])]
            for column in columns if _column(column, "name") in missing
        }
        row["source_coverage"] = {
            "scope": "captured_record",
            "additional_details": retained,
            "detail_sections": group_source_details(retained),
            "related_fields": {field: items for field, items in related.items() if items},
            "mapped_fields": len(names) - len(missing),
            "missing_fields": missing,
            "omitted_details": max(0, len(details) - len(retained)) + oversized,
            "note": (
                "Additional source details are captured quotes grouped for readability, not confirmed answers to missing fields or verified filter matches. Missing means not extracted, not absent from the website. Longer text and overflow may remain in source evidence."
                if groups else
                "No unique captured record container could be bound. Missing means not extracted; source availability is unconfirmed."
            ),
        }
    return result
