"""Choose a source identity consistently for validation and detail reconciliation."""

IDENTITY_FIELDS = (
    "article_title",
    "headline",
    "hotel_name",
    "name",
    "title",
    "article_headline",
    "article_name",
    "hotel_title",
    "property_name",
    "listing_title",
    "product_name",
    "link_title",
    "heading",
)
CLASSIFICATION_FIELDS = {
    "article_type",
    "content_type",
    "record_type",
    "item_type",
    "type",
    "category",
    "section",
    "topic_tags",
    "topic",
    "relevance",
}


def identity_field(names):
    """Prefer declared names/titles; never prefer a type label just due to column order.

    This selects a field, not an invented value. The chosen cell still requires source
    evidence. Single-field schemas (such as prices-only extraction) remain supported.
    """
    for field in IDENTITY_FIELDS:
        if field in names:
            return field
    for field in names:
        if field.endswith(("_title", "_headline", "_name")):
            return field
    return next((field for field in names if field not in CLASSIFICATION_FIELDS), names[0])
