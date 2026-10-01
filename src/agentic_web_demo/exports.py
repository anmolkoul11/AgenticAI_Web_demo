"""Reusable, bounded exports. No network, model calls or local export-file writes."""

import csv
import io
import json
import math
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation

import xlsxwriter

MAX_ROWS = 10_000
MAX_COLUMNS = 128
MAX_CELLS = 200_000
HOTEL_COLUMNS = [
    "listing_id",
    "title",
    "city",
    "check_in",
    "check_out",
    "price",
    "currency",
    "rating",
    "rating_scale",
    "price_basis",
    "source_url",
    "extracted_at",
]
CONTENT_TYPES = {
    "csv": "text/csv; charset=utf-8",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "json": "application/json",
    "jsonl": "application/x-ndjson",
}


class ExportError(ValueError):
    """Messages are fixed/safe to display; do not include source values."""


def stringify(value):
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def csv_text(value):
    text = stringify(value)
    # Apply to headers and values. No formulas are intentionally generated.
    if text.lstrip(" \t\r\n\v\f\ufeff").startswith(("=", "+", "-", "@")) or text.startswith(
        ("\t", "\r", "\n")
    ):
        return "'" + text
    return text


def dataset(payload):
    keys = [key for key in ("listings", "records") if key in payload]
    if len(keys) != 1:
        raise ExportError("Export requires one records or listings collection.")
    key = keys[0]
    rows = payload[key]
    if (
        not isinstance(rows, list)
        or len(rows) > MAX_ROWS
        or any(not isinstance(row, dict) for row in rows)
    ):
        raise ExportError("Export has invalid records or exceeds the 10,000-record limit.")
    columns = list(HOTEL_COLUMNS) if key == "listings" else []
    if key == "records" and "columns" in payload:
        declared = payload["columns"]
        if not isinstance(declared, list) or any(not isinstance(c, str) for c in declared):
            raise ExportError("Declared export columns must be a list of field names.")
        columns = list(dict.fromkeys(declared))
    for row in rows:
        for name in row:
            if name not in columns:
                columns.append(name)
    if len(columns) > MAX_COLUMNS or len(rows) * len(columns) > MAX_CELLS:
        raise ExportError("Export exceeds the 128-column or 200,000-cell limit.")
    if any(not isinstance(name, str) or not name or len(name) > 128 for name in columns):
        raise ExportError("Export field names must be non-empty text of at most 128 characters.")
    return key, columns, rows


def select_rows(rows, decisions, *, scope="all", search="", outcome="all"):
    if scope not in {"all", "filtered"} or outcome not in {"all", "matched", "unmatched"}:
        raise ExportError("Unknown export scope or outcome filter.")
    if len(search) > 200:
        raise ExportError("Export search must be at most 200 characters.")
    if scope == "all":
        return rows
    lookup = {str(d.get("listing_id")): d for d in decisions}
    selected = []
    for row in rows:
        # Match the current dashboard table's search and outcome semantics exactly.
        text = " ".join(str(row.get(k, "")) for k in ("title", "city", "listing_id"))
        decision = lookup.get(str(row.get("listing_id")), {})
        if search.lower() not in text.lower():
            continue
        if outcome == "matched" and decision.get("matched") is not True:
            continue
        if outcome == "unmatched" and decision.get("matched") is not False:
            continue
        selected.append(row)
    return selected


def _excel_value(value, column, hotel):
    # Infer types only for the existing validated hotel contract. Generic text stays text.
    if hotel and isinstance(value, str):
        if column in {"price", "rating"}:
            try:
                number = Decimal(value)
                if (
                    number.is_finite()
                    and len(number.as_tuple().digits) <= 15
                    and math.isfinite(float(number))
                ):
                    return float(number)
            except InvalidOperation:
                pass
        if column in {"check_in", "check_out"}:
            try:
                return date.fromisoformat(value)
            except ValueError:
                pass
        if column == "extracted_at":
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if parsed.tzinfo is not None:
                    return parsed.astimezone(UTC).replace(tzinfo=None)
            except ValueError:
                pass
    return value


def _write_cell(sheet, row, col, value, formats, column="", hotel=False):
    value = _excel_value(value, column, hotel)
    if value is None:
        return
    if isinstance(value, bool):
        code = sheet.write_boolean(row, col, value, formats["text"])
    elif isinstance(value, datetime):
        code = sheet.write_datetime(row, col, value, formats["datetime"])
    elif isinstance(value, date):
        code = sheet.write_datetime(row, col, value, formats["date"])
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        if len(str(value).replace(".", "").replace("-", "")) > 15 or not math.isfinite(value):
            code = sheet.write_string(row, col, str(value), formats["text"])
        else:
            kind = (
                "price"
                if hotel and column == "price"
                else "rating"
                if hotel and column == "rating"
                else "number"
            )
            code = sheet.write_number(row, col, value, formats[kind])
    else:
        text = stringify(value)
        if len(text) > 32_767:
            raise ExportError(
                "A cell exceeds Excel's text limit. Download CSV, JSON or JSON Lines instead."
            )
        code = sheet.write_string(row, col, text, formats["text"])
    if code:
        raise ExportError("A value could not be written to Excel without loss. Use JSON instead.")


def excel_bytes(columns, rows, metadata, decisions, hotel):
    output = io.BytesIO()
    with xlsxwriter.Workbook(
        output,
        {
            "in_memory": True,
            "strings_to_formulas": False,
            "strings_to_urls": False,
            "strings_to_numbers": False,
        },
    ) as workbook:
        workbook.set_properties({"title": "Extracted records", "author": "Agentic Demo Studio"})
        formats = {
            "text": workbook.add_format({"valign": "top", "text_wrap": True}),
            "number": workbook.add_format({"num_format": "0.###############", "valign": "top"}),
            "price": workbook.add_format({"num_format": "0.00", "valign": "top"}),
            "rating": workbook.add_format({"num_format": "0.0", "valign": "top"}),
            "date": workbook.add_format({"num_format": "yyyy-mm-dd", "valign": "top"}),
            "datetime": workbook.add_format({"num_format": "yyyy-mm-dd hh:mm:ss", "valign": "top"}),
        }
        header = workbook.add_format(
            {
                "bold": True,
                "bg_color": "#152F40",
                "font_color": "#FFFFFF",
                "text_wrap": True,
                "valign": "vcenter",
            }
        )

        def write_sheet(name, fields, values, typed_hotel=False):
            sheet = workbook.add_worksheet(name)
            sheet.freeze_panes(1, 0)
            sheet.hide_gridlines(2)
            sheet.set_row(0, 30)
            for col, field in enumerate(fields):
                sheet.write_string(0, col, field, header)
                width = (
                    48
                    if field in {"title", "source_url", "value", "reasons"}
                    else min(30, max(16, len(field) + 3))
                )
                sheet.set_column(col, col, width)
            for index, record in enumerate(values, 1):
                for col, field in enumerate(fields):
                    _write_cell(sheet, index, col, record.get(field), formats, field, typed_hotel)
            if fields:
                sheet.autofilter(0, 0, len(values), len(fields) - 1)
            sheet.set_landscape()
            sheet.fit_to_pages(1, 0)
            sheet.repeat_rows(0)

        write_sheet("Records", columns, rows, hotel)
        write_sheet(
            "Export info",
            ["property", "value"],
            [{"property": key, "value": value} for key, value in metadata.items()],
        )
        if decisions:
            write_sheet("Rule decisions", ["listing_id", "matched", "reasons"], decisions)
    return output.getvalue()


def build_export(
    payload, format, *, run_id, framework, decisions=(), scope="all", search="", outcome="all"
):
    if format not in CONTENT_TYPES:
        raise ExportError("Unsupported export format.")
    key, columns, original = dataset(payload)
    rows = select_rows(original, decisions, scope=scope, search=search, outcome=outcome)
    ids = {str(row.get("listing_id")) for row in rows if row.get("listing_id") is not None}
    selected_decisions = [d for d in decisions if str(d.get("listing_id")) in ids]
    if len(selected_decisions) > MAX_ROWS:
        raise ExportError("Too many rule decisions to export.")
    metadata = {
        "run_id": run_id,
        "framework": framework,
        "exported_at_utc": datetime.now(UTC).isoformat(),
        "scope": scope,
        "original_record_count": len(original),
        "exported_record_count": len(rows),
        "search_filter": search if scope == "filtered" else "",
        "outcome_filter": outcome if scope == "filtered" else "all",
        "timestamp_convention": "Excel timestamps are UTC; dates retain their calendar date.",
        "nested_values": "Objects and arrays are JSON text inside tabular cells.",
        "precision": (
            "Long numeric identifiers/text are preserved as text in Excel. "
            "Use JSON for exact source data."
        ),
    }
    if format == "json":
        data = json.dumps(
            {**payload, key: rows}, ensure_ascii=False, allow_nan=False, indent=2
        ).encode("utf-8")
    elif format == "jsonl":
        data = "".join(
            json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n" for row in rows
        ).encode("utf-8")
    elif format == "csv":
        stream = io.StringIO(newline="")
        writer = csv.writer(stream)
        if columns:
            writer.writerow([csv_text(column) for column in columns])
        writer.writerows([[csv_text(row.get(column)) for column in columns] for row in rows])
        data = stream.getvalue().encode("utf-8-sig")
    else:
        data = excel_bytes(columns, rows, metadata, selected_decisions, key == "listings")
    return data, CONTENT_TYPES[format]
