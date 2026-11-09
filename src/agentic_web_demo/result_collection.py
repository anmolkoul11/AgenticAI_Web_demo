"""Collect the observed result list, without a model decision for each scroll.

All sources remain bounded snapshots. Pagination uses only observed same-origin
result controls; returned stay scope is independently checked on every document.
"""

import copy
import re
import time

from agentic_web_demo.capture import clean_url
from agentic_web_demo.custom_fetch import WebsiteError, origin
from agentic_web_demo.browser_task import TaskLedger
from agentic_web_demo.stay_scope import (
    observed_result_scope, reconcile_captured_occupancy, reconcile_captured_result_scope,
)


MAX_RESULT_PAGES = 100
MAX_COLLECTION_SECONDS = 240


def record_groups(page):
    groups = {}
    for block in page.get("blocks", []):
        if block.get("association") == "record" and block.get("group_id"):
            groups.setdefault(block["group_id"], []).append(block)
    return groups


def record_key(blocks, url):
    headings = [item for item in blocks if item.get("kind") == "heading"]
    title = headings[0]["text"] if headings else next(
        (item["text"] for item in blocks if item.get("kind") == "link"), ""
    )
    normalize = lambda value: re.sub(r"^\d+[.)]\s*", "", " ".join(str(value).casefold().split()))
    urls = {clean_url(item["href"]) for item in blocks if item.get("href")
            and (item in headings or normalize(item["text"]) == normalize(title))}
    return ("url", next(iter(urls))) if len(urls) == 1 else (url, normalize(title))


def batch_identifiers(page, number):
    """Keep evidence IDs unique even when many windows share the same URL."""
    blocks = {block["id"]: f"b{number * 1000 + index + 1}" for index, block in enumerate(page["blocks"])}
    groups = {group: f"g{number * 1000 + index + 1}" for index, group in enumerate(record_groups(page))}
    def remap(value, key=""):
        if isinstance(value, dict):
            return {name: remap(item, name) for name, item in value.items()}
        if isinstance(value, list):
            mapping = blocks if key == "block_ids" else groups if key == "group_ids" else {}
            return [mapping.get(item, item) if isinstance(item, str) else remap(item) for item in value]
        return groups.get(value, value) if key == "group_id" and isinstance(value, str) else value
    page = remap(page)
    for block in page["blocks"]:
        block["id"] = blocks[block["id"]]
    return page


class ResultCollector:
    def __init__(self, tools, values, initial_pages, progress):
        self.tools, self.values, self.initial_pages, self.progress = tools, values, initial_pages, progress
        # Pagination belongs to collection, after navigation has verified the
        # search. It must not displace calendar days or destination suggestions.
        self.tools.focus = "collection"
        self.pages, self.seen, self.windows, self.pagination_attempts = [], set(), set(), set()
        self.records, self.batch_number = {}, 0
        self.documents, self.empty_rounds, self.active_seconds = set(), 0, 0
        self.unbound_groups = 0
        self.complete, self.reason = False, "not_started"
        self.guidance = ""
        self.last_position = None
        self._started, self.pending_transition = None, None
        self.rewind_needed, self.rewind_position, self.page_number = True, None, 1
        context = tools.collection_context or {}
        self.preview_anchor = copy.deepcopy(context) if (
            context.get("status") == "form_verified_search_submitted"
            and context.get("scope") == "form_values_and_submission_only"
            and context.get("result_state") == "observed"
            and context.get("source_preview_only") is True
            and context.get("result_document_id") and context.get("result_url")
            and (context.get("result_scope") or {}).get("requested")
        ) else None
        self.source_preview_only = False
        self.scope_diagnostics = {}
        self.scope_snapshot = None

    def summary(self):
        return {"scope": "observed_result_list", "mode": "all_results", "complete": self.complete,
                "guidance": self.guidance,
                "source_preview_only": any((page.get("browser_task_context") or {}).get("source_preview_only")
                                           for page in self.pages) if self.pages else self.source_preview_only,
                **self.scope_diagnostics,
                "reason": self.reason, "records_collected": len(self.seen), "source_batches": len(self.pages),
                "result_pages": len(self.documents), "record_limit": self.values.record_limit,
                "unbound_source_observations": self.unbound_groups,
                "page_limit": MAX_RESULT_PAGES, "active_seconds": round(self.active_seconds +
                    (time.monotonic() - self._started if self._started is not None else 0), 1)}

    def output(self):
        self.progress(self.summary())
        pages = copy.deepcopy(self.pages or self.initial_pages)
        for page in pages:
            page["result_collection"] = self.summary()
        return pages

    def action(self, name, control_id=None, value=""):
        from agentic_web_demo.browser_agent import BrowserDecision
        self.tools.guard()
        return self.tools.execute(BrowserDecision(
            action=name, control_id=control_id, value=value, purpose="other",
            explanation="Continue collecting the current result list.",
            evidence="Only observed result controls and passive scrolling are used.",
        ))

    def verify_scope(self, observation):
        self.scope_snapshot = None
        task = TaskLedger(self.values.instructions)
        if not task.requested_stay:
            return observation
        context = self.tools.collection_context or {}
        scope = observed_result_scope(task.requested_stay, observation)
        if context.get("result_document_id") == observation.get("document_id"):
            previous_scope = context.get("result_scope") or {}
            contradictions = copy.deepcopy(previous_scope.get("contradictions") or [])
            contradictions.extend(item for item in scope.get("contradictions", []) if item not in contradictions)
            scope["contradictions"] = contradictions[:24]
            if previous_scope.get("status") == "mismatch" or any(
                isinstance(item, dict) and item.get("code") != "catalog_starting_price"
                for item in contradictions
            ):
                scope["status"] = "mismatch"
            elif contradictions:
                scope["status"] = "unverified"
        retained = reconcile_captured_occupancy(scope, context, observation)
        self.describe_scope(retained)
        if retained.get("status") == "verified" and context.get("result_document_id") == observation.get("document_id"):
            self.tools.collection_context = {
                **copy.deepcopy(context), "result_scope": copy.deepcopy(retained),
                "requested_stay_verified": True, "source_preview_only": False,
            }
            return observation
        earlier = context.get("result_scope") or {}
        earlier_destination = next((item for item in earlier.get("fields", [])
                                    if item.get("field") == "destination"), {})
        missing = [item.get("field") for item in retained.get("fields", []) if item.get("status") != "verified"]
        if (
            retained.get("status") == "unverified" and missing == ["destination"]
            and not retained.get("contradictions") and not earlier.get("contradictions")
            and earlier.get("status") == "verified" and context.get("requested_stay_verified") is True
            and "captured_results_heading" in {item.strip() for item in str(earlier_destination.get("method", "")).split(",")}
            and context.get("result_document_id") == observation.get("document_id")
            and context.get("result_url") == observation.get("url")
            and (observation.get("results") or {}).get("record_count", 0) > 0
            and not (observation.get("results") or {}).get("busy")
        ):
            # The control inventory may omit a returned page heading that the
            # source collector can read. Re-read it; the earlier quote only
            # authorizes this passive inspection and never supplies new proof.
            snapshot = self.tools.capture_records(0)
            captured = snapshot.get("browser_task_context") or {}
            fresh = copy.deepcopy(captured.get("result_scope") or {})
            if (
                captured.get("result_document_id") == observation.get("document_id")
                and captured.get("result_url") == observation.get("url")
                and clean_url(snapshot["url"]) == clean_url(observation["url"])
                and fresh.get("requested") == retained.get("requested")
                and fresh.get("source") == "returned_page"
                and isinstance(fresh.get("observed"), dict)
                and {item.get("field") for item in fresh.get("fields", [])} ==
                    {item.get("field") for item in retained.get("fields", [])}
                and not fresh.get("contradictions")
                and all(item.get("status") == "verified" for item in fresh.get("fields", [])
                        if item.get("field") != "destination")
                and not any(item.get("status") == "mismatch" for item in fresh.get("fields", []))
            ):
                # Remove any inherited destination quote before reconciling the
                # newly captured heading; missing/conflicting headings fail.
                fresh["fields"] = [item for item in fresh.get("fields", []) if item.get("field") != "destination"]
                fresh["observed"].pop("destination", None)
                fresh["status"] = "unverified"
                fresh = reconcile_captured_result_scope(fresh, snapshot.get("blocks", []),
                                                        document_id=observation["document_id"])
                if fresh.get("status") == "verified":
                    captured.update(result_scope=fresh, requested_stay_verified=True, source_preview_only=False)
                    snapshot["browser_task_context"] = captured
                    self.tools.collection_context = copy.deepcopy(captured)
                    self.scope_snapshot = snapshot
                    self.describe_scope(fresh)
                    return observation
            raise WebsiteError("The current captured result heading did not confirm the requested destination. Review the result page before resuming.")
        if self.preview_allowed(observation, scope):
            # The agent already confirmed a real Search and intentionally handed
            # off these returned sources without claiming requested-stay proof.
            # Capture them for review; never promote pre-search values to proof.
            preview_scope = copy.deepcopy(scope)
            earlier_scope = context.get("result_scope") or {}
            contradictions = copy.deepcopy(earlier_scope.get("contradictions") or [])
            contradictions.extend(item for item in scope.get("contradictions", []) if item not in contradictions)
            preview_scope["contradictions"] = contradictions[:24]
            if earlier_scope.get("status") == "mismatch":
                preview_scope["status"] = "mismatch"
            self.tools.collection_context = {
                **copy.deepcopy(context), "result_scope": preview_scope,
                "requested_stay_verified": False, "source_preview_only": True,
                "availability_verified": False, "record_values_verified": False,
            }
            self.describe_scope(preview_scope)
            self.source_preview_only = True
            return observation
        task.observe(observation)
        if not task.adopt_matching_results(observation):
            diagnostic = task.occupancy_recheck(observation, include_verified=True)
            if diagnostic:
                self.action("click", diagnostic["opener"]["control_id"])
                observation = self.tools.observe()
                task.observe(observation)
                proof = task.confirm_occupancy_inspection(observation, diagnostic)
                if not proof or not task.adopt_matching_results(observation, post_commit_inspection=proof):
                    raise WebsiteError("The returned result page did not confirm the requested stay. Review its dates and guests before resuming.")
            else:
                raise WebsiteError("Requested stay details could not be verified on this result page. Review its dates and guests before resuming.")
        self.tools.collection_context = task.capture_context(observation)
        self.describe_scope((self.tools.collection_context or {}).get("result_scope") or scope)
        return observation

    def describe_scope(self, scope):
        self.scope_diagnostics = {
            "scope_status": scope.get("status", "unverified"),
            "scope_fields": [
                {"field": item["field"],
                 "expected": str(item["expected"])[:240] if item.get("expected") is not None else None,
                 "observed": str(item["observed"])[:240] if item.get("observed") is not None else None,
                 "status": item.get("status"), "method": str(item.get("method", "none"))[:100],
                 "evidence": [
                     {"method": str(method)[:60], "value": str(value.get("value", ""))[:240],
                      "quote": str(value.get("evidence", ""))[:180]}
                     for method, values in (item.get("evidence_by_method") or {}).items()
                     if isinstance(values, list) for value in values[:4] if isinstance(value, dict)
                 ][:4]}
                for item in scope.get("fields", [])
                if item.get("field") in {"destination", "check_in", "check_out", "adults", "children", "rooms"}
            ][:6],
            "unverified_fields": [item["field"] for item in scope.get("fields", [])
                                  if item.get("status") == "unverified"][:8],
            "mismatched_fields": [item["field"] for item in scope.get("fields", [])
                                  if item.get("status") == "mismatch"][:8],
            "contradiction_codes": list(dict.fromkeys(
                item["code"] for item in scope.get("contradictions", [])
                if isinstance(item, dict) and isinstance(item.get("code"), str)
            ))[:12],
        }

    def preview_allowed(self, observation, scope):
        anchor = self.preview_anchor
        facts = observation.get("results") or {}
        if not (
            anchor and self.page_number == 1
            and observation.get("document_id") == anchor["result_document_id"]
            and observation.get("url") == anchor["result_url"]
            and facts.get("record_count", 0) > 0 and not facts.get("busy")
            and scope.get("status") in {"unverified", "mismatch"}
        ):
            return False
        # This permits a read-only source capture, not a matching-stay claim.
        # A captured heading may disappear from the narrower control inventory;
        # room evidence may also gain another value or change ordering as the
        # same result page renders. Those changes must remain review evidence,
        # rather than being mistaken for navigation to another searched page.
        # The confirmed document/URL above and the original requested stay bind
        # this exception; downstream review still rejects unknown/mismatched data.
        earlier = anchor.get("result_scope") or {}
        return (scope.get("source") == "returned_page"
                and bool(scope.get("requested"))
                and scope.get("requested") == earlier.get("requested"))

    def retain(self, page):
        keep, chosen = set(), {}
        for group, blocks in record_groups(page).items():
            key = record_key(blocks, page["url"])
            quality = (((page.get("browser_task_context") or {}).get("result_scope") or {}).get("status") == "verified",
                       any(re.search(r"[$€£]|\b(?:USD|EUR|GBP|CAD|AUD|JPY)\b", block["text"]) for block in blocks),
                       len(blocks), min(sum(len(block["text"]) for block in blocks), 4000))
            previous = self.records.get(key)
            if key[1] and (key not in self.seen and len(self.seen) < self.values.record_limit
                           or previous and quality > previous[2]):
                if previous:
                    old_page, old_group, _ = previous
                    old_page["blocks"] = [block for block in old_page["blocks"] if block.get("group_id") != old_group]
                    old_page["text"] = "\n".join(block["text"] for block in old_page["blocks"])
                    old_page["coverage"].update(record_groups=len(record_groups(old_page)),
                        records_selected=len(record_groups(old_page)),
                        captured_text_chars=sum(len(block["text"]) for block in old_page["blocks"]))
                self.seen.add(key)
                keep.add(group)
                chosen[group] = (key, quality)
        if not keep:
            return
        page = copy.deepcopy(page)
        page["blocks"] = [block for block in page["blocks"] if block.get("association") == "page"
                          or block.get("group_id") in keep]
        page["text"] = "\n".join(block["text"] for block in page["blocks"])
        self.batch_number += 1
        aliases = {group: f"g{self.batch_number * 1000 + index + 1}" for index, group in enumerate(record_groups(page))}
        page = batch_identifiers(page, self.batch_number)
        page["capture_id"] = f"result-batch-{self.batch_number:04d}"
        page.setdefault("coverage", {}).update(
            captured_text_chars=sum(len(block["text"]) for block in page["blocks"]),
            record_groups=len(keep), records_selected=len(keep)
        )
        self.pages = [previous for previous in self.pages if record_groups(previous)]
        self.pages.append(page)
        self.records.update({key: (page, aliases[group], quality) for group, (key, quality) in chosen.items()})
        self.progress(self.summary())

    def run(self):
        started = time.monotonic()
        self._started = started
        try:
            self.reason = "collecting"
            self.guidance = ""
            while self.active_seconds + time.monotonic() - started < MAX_COLLECTION_SECONDS:
                self.tools.guard()
                observation = self.tools.observe()
                document = observation.get("document_id", observation.get("url"))
                facts = observation.get("results") or {}
                identity = facts.get("record_set_signature") or facts.get("result_signature")
                if self.pending_transition and identity == self.pending_transition["before"]:
                    self.pending_transition["waits"] += 1
                    if self.pending_transition["waits"] >= 8:
                        raise WebsiteError("The next-page response is unconfirmed. Inspect the website before resuming; the pagination click will not be repeated.")
                    self.action("wait")
                    continue
                if self.pending_transition and self.pending_transition["kind"] == "next":
                    self.page_number += 1
                self.pending_transition = None
                if facts.get("busy"):
                    self.action("wait")
                    self.empty_rounds += 1
                    if self.empty_rounds >= 12:
                        raise WebsiteError("The result list is still updating. Wait for it to settle, then Resume.")
                    continue
                self.empty_rounds = 0
                viewport = (observation.get("frames") or [{}])[0].get("viewport") or {}
                if self.rewind_needed:
                    position = viewport.get("scroll_y", 0)
                    if position > 0:
                        if position == self.rewind_position:
                            self.reason = "scroll_stalled"
                            return self.output()
                        self.rewind_position = position
                        self.action("scroll", value="up")
                        continue
                    self.rewind_needed, self.rewind_position = False, None
                observation = self.verify_scope(observation)
                self.documents.add((document, self.page_number))
                if facts.get("no_results") and not facts.get("record_count"):
                    self.complete = bool(self.seen) and not self.unbound_groups
                    self.reason = "end_of_available_results" if self.complete else "unbound_source_cards"
                    return self.output()
                signature = (document, facts.get("result_signature"), facts.get("record_count"),
                             ((self.tools.collection_context or {}).get("result_scope") or {}).get("status"))
                if signature not in self.windows:
                    offset = 0
                    while True:
                        if offset == 0 and self.scope_snapshot is not None:
                            snapshot, self.scope_snapshot = self.scope_snapshot, None
                        else:
                            snapshot = self.tools.capture_records(offset)
                        captured_context = snapshot.get("browser_task_context") or {}
                        if self.source_preview_only and not captured_context.get("result_document_id"):
                            raise WebsiteError("The captured result preview lost its document-bound stay context. Inspect the current results before resuming.")
                        scope = captured_context.get("result_scope") or {}
                        if scope.get("requested") and scope.get("status") != "verified":
                            anchor = self.preview_anchor or {}
                            fresh = self.tools.observe()
                            fresh_scope = observed_result_scope((anchor.get("result_scope") or {}).get("requested") or {}, fresh)
                            self.describe_scope(fresh_scope)
                            preview = (
                                self.source_preview_only and captured_context.get("source_preview_only") is True
                                and captured_context.get("result_document_id") == anchor.get("result_document_id")
                                and clean_url(snapshot["url"]) == clean_url(anchor.get("result_url", snapshot["url"]))
                                and self.preview_allowed(fresh, fresh_scope)
                            )
                            if not preview:
                                raise WebsiteError("The stay changed during collection. Inspect the current results before resuming.")
                            self.describe_scope(scope)
                        coverage = snapshot.get("coverage") or {}
                        if not coverage.get("record_window"):
                            raise WebsiteError("Reload the updated Browser Companion before collecting all results.")
                        if not coverage.get("records_selected"):
                            self.reason = "record_layout_unavailable"
                            return self.output()
                        self.unbound_groups += max(0, coverage["records_selected"] - len(record_groups(snapshot)))
                        self.retain(snapshot)
                        if len(self.seen) >= self.values.record_limit:
                            self.reason = "record_limit"
                            return self.output()
                        offset += 10
                        if offset >= coverage.get("records_detected", 0):
                            break
                    self.windows.add(signature)
                observation = self.tools.observe()
                viewport = (observation.get("frames") or [{}])[0].get("viewport") or {}
                position = (document, viewport.get("scroll_y"), viewport.get("document_height"),
                            observation.get("results", {}).get("record_set_signature") or observation.get("results", {}).get("result_signature"))
                stable = position == self.last_position
                self.last_position = position
                if not viewport.get("at_page_end"):
                    self.action("scroll", value="down")
                    if stable:
                        self.reason = "scroll_stalled"
                        return self.output()
                    continue
                if not stable:
                    self.action("wait")
                    continue
                candidates = [item for frame in observation.get("frames", []) for item in frame.get("controls", [])
                              if item.get("pagination") in {"next", "more"} and item.get("enabled", True)]
                destinations = {item.get("href") or item.get("label") for item in candidates}
                if not candidates:
                    self.complete = bool(self.seen) and not self.unbound_groups
                    self.reason = "end_of_available_results" if self.complete else "unbound_source_cards"
                    return self.output()
                if len(destinations) != 1:
                    self.reason = "ambiguous_pagination"
                    return self.output()
                target = candidates[0]
                if self.source_preview_only and self.preview_anchor and (
                    (self.tools.collection_context or {}).get("result_scope") or {}
                ).get("status") != "verified":
                    self.reason = "unverified_stay_pagination"
                    self.guidance = "Captured this result page as source previews. Verify the returned stay before collecting another result page."
                    return self.output()
                if target.get("href") and origin(target["href"]) != self.tools.approved_origin:
                    self.reason = "external_pagination"
                    return self.output()
                next_identity = observation.get("results", {}).get("record_set_signature") or observation.get("results", {}).get("result_signature")
                cursor = (document, next(iter(destinations)), next_identity)
                if cursor in self.pagination_attempts or len(self.documents) >= MAX_RESULT_PAGES:
                    self.reason = "pagination_stalled" if cursor in self.pagination_attempts else "page_limit"
                    return self.output()
                self.pagination_attempts.add(cursor)  # An uncertain click is never replayed.
                self.pending_transition = {"before": next_identity,
                                           "kind": target["pagination"], "waits": 0}
                self.rewind_needed = target["pagination"] == "next"
                self.action("click", target["id"])
                self.action("wait")
                self.last_position = None
            self.reason = "collection_time_limit"
            return self.output()
        finally:
            self.active_seconds += time.monotonic() - started
            self._started = None

