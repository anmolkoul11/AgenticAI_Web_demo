"""Extract disjoint source batches once, retaining one output-field contract."""

import copy

from openai import APIError

from agentic_web_demo.custom_fetch import WebsiteError
from agentic_web_demo.record_identity import identity_field
from agentic_web_demo.source_fields import article_content, normalized


def interpret_result_batches(values, pages, settings, interpret, progress, alive):
    candidates, metadata, fields = [], [], list(values.output_fields)
    failure, coverage, failures, failed_candidate = None, [], [], None
    for index, page in enumerate(pages):
        if not alive():
            raise WebsiteError("Collection was cancelled before the next extraction batch.")
        progress(f"Extracting listings: batch {index + 1} of {len(pages)}.")
        groups = {block.get("group_id") for block in page.get("blocks", [])
                  if block.get("association") == "record" and block.get("group_id")}
        batch_limit = min(10, max(len(groups), 1)) if page.get("coverage", {}).get("record_window") else min(50, values.record_limit)
        batch_values = values.model_copy(update={"record_limit": batch_limit, "output_fields": fields})
        try:
            candidate, details = interpret(batch_values, [page], settings, column_contract=(
                [column.model_dump() for column in candidates[0].columns] if candidates else None
            ))
        except (APIError, WebsiteError):
            if not candidates:
                raise
            failure = {"batch": index + 1, "reason": "batch_failed_no_retry"}
            failures.append(failure)
            break
        metadata.append(details)
        if candidate.outcome != "ready":
            failure = {"batch": index + 1, "reason": "batch_needs_attention"}
            failures.append(failure)
            failed_candidate = candidate
            continue  # A different source batch may contain the requested records.
        if not fields:
            fields = [column.name for column in candidate.columns]
        identity = identity_field([column.name for column in candidate.columns])
        article_rows = article_content(candidate.content_type) or article_content(values.instructions)
        covered = set()
        for row in candidate.rows:
            if article_rows and row.headline_block_id:
                # A repeated programme label can occur on many episode cards.
                # The selected literal headline binds this returned row to one
                # source group; source validation checks that choice afterward.
                selected = [block for block in page.get("blocks", [])
                            if block.get("id") == row.headline_block_id
                            and block.get("kind") in {"heading", "link"}
                            and block.get("association") == "record" and block.get("group_id")]
                if len(selected) == 1:
                    covered.add(selected[0]["group_id"])
                continue
            cell = next((cell for cell in row.cells if cell.field == identity and cell.value), None)
            if cell:
                covered.update(block["group_id"] for block in page.get("blocks", [])
                               if block.get("group_id") and normalized(cell.value) in normalized(block["text"])
                               and (block.get("kind") in {"heading", "link", "table_row"}
                                    or article_rows
                                    and normalized(cell.value) == normalized(block["text"])))
        coverage.append({"batch": index + 1, "source_groups": len(groups), "returned_groups": len(covered & groups),
                         "unreturned_groups": len(groups - covered)})
        for row in candidate.rows:
            if row.page_index != 0:
                raise WebsiteError("An extraction batch referenced a source it did not receive.")
            row.page_index = index
        candidates.append(candidate)
    if not candidates:
        if failed_candidate is not None:
            result = copy.deepcopy(metadata[0])
            result.update(extraction_batches={"completed": 0, "total": len(pages), "complete": False, "failures": failures})
            result["usage"] = {key: sum(int(item.get("usage", {}).get(key) or 0) for item in metadata)
                               for key in ("input_tokens", "output_tokens", "total_tokens")}
            return failed_candidate, result
        raise WebsiteError("There were no source batches to extract.")
    first = candidates[0]
    wanted = {column.name: column.kind for column in first.columns}
    if any({column.name: column.kind for column in item.columns} != wanted for item in candidates[1:]):
        raise WebsiteError("Extraction batches returned incompatible output fields. No merged result was saved.")
    warnings = list(dict.fromkeys(warning for item in candidates for warning in item.warnings))
    if failure:
        warnings.insert(0, f"Extraction batch {failure['batch']} needs attention; some collected sources have no extracted rows. No automatic retry.")
    missing = sum(item["unreturned_groups"] for item in coverage)
    if missing:
        warnings.insert(0, f"{missing} captured source cards were not returned as model candidates. This may include unrelated cards; review coverage before treating the result set as complete.")
    rows = [row for item in candidates for row in item.rows]
    combined = first.model_copy(update={
        "rows": rows, "warnings": warnings[:10],
        "more_records_available": bool(failure or missing),
    })
    usage = {key: sum(int(item.get("usage", {}).get(key) or 0) for item in metadata)
             for key in ("input_tokens", "output_tokens", "total_tokens")}
    usage["input_tokens_details"] = {"cached_tokens": sum(
        int((item.get("usage", {}).get("input_tokens_details") or {}).get("cached_tokens") or 0)
        for item in metadata
    )}
    result = copy.deepcopy(metadata[0])
    result.update(usage=usage, extraction_batches={
        "completed": len(candidates), "total": len(pages), "complete": not failure and not missing,
        "candidates": len(rows), "failure": failure,
        "failures": failures,
        "source_coverage": coverage, "unreturned_groups": missing,
        "batch_usage": [item.get("usage", {}) for item in metadata],
    })
    return combined, result

