"""Navigation projection never changes live references or source evidence."""

import copy
import json

import pytest

from agentic_web_demo.browser_context import build_navigation_context, screenshot_selection


def payload(controls, *, pending=None, requirements=None, dates=None, text="Page content"):
    return {
        "task": "Find hotels in New York for 3 adults and 2 rooms, October 28-30, 2026.",
        "reference_date": "2026-10-12",
        "observation": {
            "url": "https://example.org/",
            "document_id": "document-one",
            "frames": [{"url": "https://example.org/", "text": text, "controls": controls}],
            "captured_urls": [],
        },
        "task_checklist": {
            "requirements": requirements or [],
            "pending_fields": ["destination", "check_in", "check_out", "adults", "rooms"]
            if pending is None
            else pending,
            "visible_date_choices": dates or [],
            "search_submitted": False,
            "search_response_pending": False,
            "date_resolution": {
                "policy": "current_year_if_valid",
                "year": 2026,
                "check_in": "2026-10-28",
                "check_out": "2026-10-30",
            },
        },
        "recent_actions": [
            {
                "step": index,
                "action": "click",
                "control": "Old control",
                "status": "done",
                "evidence": "Long old quote " * 400,
                "counter_evidence": {"stale_id": "99:99"},
            }
            for index in range(20)
        ],
        "last_transition": {
            "status": "change_observed",
            "widget_changed": True,
            "new_controls": [{"id": "stale:123", "context": "Old context " * 500}],
        },
        "budget": {"remaining_calls": 20, "remaining_seconds": 200, "max_pages": 6},
    }


def all_controls(context):
    return [item for frame in context["observation"]["frames"] for item in frame["controls"]]


def size(value):
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")))


def test_collection_goal_and_capture_memory_fit_navigation_context_without_mutation():
    values = payload([], pending=[])
    values["task"] = "Find sports content and open relevant pages for their context."
    values["requested_output_fields"] = ["headline", "source_url", "context"]
    values["collection_goal_required"] = True
    values["task_checklist"].update(
        collection_mode="linked_details",
        collection_goal={
            "mode": "linked_details",
            "request_quote": "open relevant pages",
            "reason": "The user requested context from linked sources.",
        },
        collection_progress={
            "sources": [
                {"url": f"https://example.org/detail/{index}", "kind": "detail"}
                for index in range(5)
            ],
            "captured_pages": 5,
            "detail_pages": 5,
            "max_pages": 6,
            "max_detail_pages": 5,
            "coverage": "Bounded captures, not every website record.",
        },
    )
    baseline = copy.deepcopy(values)
    result = build_navigation_context(values)
    assert result["task_checklist"]["collection_goal"]["mode"] == "linked_details"
    assert result["requested_output_fields"] == values["requested_output_fields"]
    assert result["collection_goal_required"] is True
    assert len(result["task_checklist"]["collection_progress"]["sources"]) == 5
    assert result["task_checklist"]["collection_progress"]["detail_pages"] == 5
    assert "request_quote" not in result["task_checklist"]["collection_goal"]
    assert values == baseline
    assert size(result) <= 14000


def test_long_capture_url_is_disclosed_as_omitted_not_a_fake_shortened_link():
    values = payload([], pending=[])
    values["task_checklist"]["collection_progress"] = {
        "sources": [{"url": "https://example.org/" + "x" * 1000, "kind": "page"}],
        "captured_pages": 1,
    }
    result = build_navigation_context(values)
    source = result["task_checklist"]["collection_progress"]["sources"][0]
    assert "url" not in source
    assert source["url_omitted"] is True
    assert len(source["url_fingerprint"]) == 16


@pytest.mark.parametrize("mode", ["current_page", "search_results", "linked_details"])
def test_generic_collection_modes_survive_projection(mode):
    values = payload([], pending=[])
    values["task_checklist"]["collection_mode"] = mode
    result = build_navigation_context(values)
    assert result["task_checklist"]["collection_mode"] == mode


def test_optional_information_feedback_is_compact_and_does_not_rewrite_the_task():
    values = payload([], pending=[])
    values["task"] = "Get articles related to world politics."
    values["task_checklist"]["information_need_feedback"] = [
        {"field": f"inferred_{index}", "status": "ignored",
         "reason": "not_requested_navigation_need"}
        for index in range(8)
    ]
    baseline = copy.deepcopy(values)
    result = build_navigation_context(values)
    assert result["task"] == baseline["task"]
    assert result["task_checklist"]["information_need_feedback"] == (
        baseline["task_checklist"]["information_need_feedback"][-3:]
    )
    assert values == baseline
    assert size(result) <= 14000


def test_navigation_context_retains_task_and_is_not_a_delta_or_source_mutation():
    values = payload(
        [
            {
                "id": "0:4",
                "tag": "INPUT",
                "label": "Destination",
                "value": "New York",
                "context": "Duplicate parent " * 100,
                "numeric_probe": {"child_buttons": 0},
            },
        ],
        text="Complete original source " * 2000,
    )
    baseline = copy.deepcopy(values)
    result = build_navigation_context(values)
    assert values == baseline
    assert result["task"] == values["task"]
    assert result["reference_date"] == values["reference_date"]
    assert result["budget"] == values["budget"]
    assert (
        result["task_checklist"]["date_resolution"] == values["task_checklist"]["date_resolution"]
    )
    assert all_controls(result)[0]["id"] == "0:4"
    assert "numeric_probe" not in all_controls(result)[0]
    assert "context" not in all_controls(result)[0]
    assert len(result["recent_actions"]) == 3
    assert "evidence" not in result["recent_actions"][-1]
    assert "new_controls" not in result["last_transition"]
    assert result["observation"]["context_coverage"]["text_chars_omitted"] > 0
    assert size(result) <= 14000
    assert size(result["observation"]) <= 8000


def test_requested_late_calendar_choices_and_associated_options_have_priority():
    controls = [
        {
            "id": f"0:{index}",
            "tag": "A",
            "label": f"Background page {index}",
            "href": f"https://example.org/long/{index}",
            "text": "Background " * 80,
        }
        for index in range(100)
    ]
    controls += [
        {
            "id": "0:calendar-28",
            "tag": "SPAN",
            "role": "checkbox",
            "label": "Wednesday, October 28, 2026",
            "date": "2026-10-28",
        },
        {
            "id": "0:calendar-30",
            "tag": "SPAN",
            "role": "checkbox",
            "label": "Friday, October 30, 2026",
            "date": "2026-10-30",
        },
        {
            "id": "0:field",
            "tag": "INPUT",
            "role": "combobox",
            "label": "Destination",
            "value": "New York",
            "expanded": "true",
            "selection_required": True,
            "option_ids": ["0:city", "0:airport"],
        },
        {
            "id": "0:city",
            "tag": "BUTTON",
            "role": "option",
            "option_primary": "New York",
            "label": "New York, United States of America",
        },
        {
            "id": "0:airport",
            "tag": "BUTTON",
            "role": "option",
            "label": "LaGuardia Airport New York, United States",
        },
        {
            "id": "0:increase",
            "tag": "BUTTON",
            "label": "increase Adults",
            "counter": {
                "label": "Adults",
                "value": 2,
                "direction": "increase",
                "method": "button",
                "evidence": "Repeated long row " * 60,
            },
        },
    ]
    values = payload(
        controls,
        dates=[
            {"field": "check_in", "date": "2026-10-28", "control_id": "0:calendar-28"},
            {"field": "check_out", "date": "2026-10-30", "control_id": "0:calendar-30"},
        ],
    )
    result = build_navigation_context(values)
    selected = {item["id"]: item for item in all_controls(result)}
    assert {
        "0:calendar-28",
        "0:calendar-30",
        "0:field",
        "0:city",
        "0:airport",
        "0:increase",
    } <= selected.keys()
    assert selected["0:field"]["option_ids"] == ["0:city", "0:airport"]
    assert selected["0:increase"]["counter"] == {
        "label": "Adults",
        "value": 2,
        "direction": "increase",
        "method": "button",
    }
    assert result["observation"]["context_coverage"]["controls_omitted"] > 0
    assert result["observation"]["context_coverage"]["requested_controls_omitted"] == 0


def test_news_context_keeps_link_urls_and_a_bounded_current_page_summary():
    controls = [
        {
            "id": f"0:{index}",
            "tag": "A",
            "label": f"Science headline {index}",
            "href": f"https://example.org/research/{index}",
            "context": "Paragraph " * 100,
        }
        for index in range(140)
    ]
    values = payload(controls, pending=[], text="Research index text " * 1000)
    values["task"] = "Find relevant scientific research and open the relevant detail pages."
    result = build_navigation_context(values)
    kept = all_controls(result)
    assert len(kept) >= 15
    assert all(item["href"].startswith("https://example.org/research/") for item in kept)
    assert 0 < len(result["observation"]["frames"][0]["text"]) <= 1400
    assert result["observation"]["context_coverage"]["controls_omitted"] > 0
    assert size(result) <= 14000


def test_relevant_late_links_take_priority_without_inventing_relevance():
    controls = [
        {
            "id": f"0:{index}",
            "tag": "A",
            "label": f"Unrelated shopping item {index}",
            "href": f"https://example.org/shopping/{index}",
        }
        for index in range(140)
    ]
    controls.append(
        {
            "id": "0:soccer",
            "tag": "A",
            "label": "Soccer championship update",
            "href": "https://example.org/sport/soccer-championship",
        }
    )
    values = payload(controls, pending=[])
    values["task"] = "Find relevant articles about soccer."
    result = build_navigation_context(values)
    assert all_controls(result)[0]["id"] == "0:soccer"
    assert "relevant" not in all_controls(result)[0]


def test_navigation_retains_viewport_rect_and_open_widget_for_optional_images():
    values = payload(
        [
            {
                "id": "0:0",
                "tag": "BUTTON",
                "label": "",
                "rect": {"x": 100, "y": 200, "width": 40, "height": 30},
            }
        ]
    )
    frame = values["observation"]["frames"][0]
    frame["viewport"] = {"width": 1280, "height": 720, "scroll_y": 0}
    frame["widgets"] = [{"role": "dialog", "label": "Travelers", "text": "Adults Rooms"}]
    values["observation"]["version"] = 4
    result = build_navigation_context(values)
    assert result["observation"]["version"] == 4
    assert result["observation"]["frames"][0]["viewport"] == frame["viewport"]
    assert result["observation"]["frames"][0]["widgets"][0]["label"] == "Travelers"
    assert all_controls(result)[0]["rect"] == frame["controls"][0]["rect"]


def test_news_words_are_not_misclassified_as_form_controls():
    values = payload(
        [
            {
                "id": f"0:{index}",
                "tag": "A",
                "label": f"Candidate celebrating world update {index}",
                "href": f"https://example.org/world/update-{index}",
            }
            for index in range(100)
        ]
        + [
            {
                "id": "0:soccer",
                "tag": "A",
                "label": "Soccer championship update",
                "href": "https://example.org/sport/soccer",
            }
        ],
        pending=[],
    )
    values["task"] = "Find soccer stories."
    result = build_navigation_context(values)
    assert all_controls(result)[0]["id"] == "0:soccer"


def test_declared_site_alias_and_plural_topic_help_prioritize_links():
    values = payload(
        [
            {"id": "0:0", "tag": "A", "label": "Shopping", "href": "https://example.org/shop"},
            {"id": "0:1", "tag": "A", "label": "Football", "href": "https://example.org/football"},
            {"id": "0:2", "tag": "A", "label": "Sport", "href": "https://example.org/sport"},
        ],
        pending=[],
        requirements=[
            {
                "field": "topic",
                "expected": "football",
                "model_interpreted": True,
                "application": "form",
                "status": "verified",
                "observed": "football",
            }
        ],
    )
    values["task"] = "Find soccer sports stories."
    result = build_navigation_context(values)
    assert [item["id"] for item in all_controls(result)][:2] == ["0:1", "0:2"]
    assert result["task_checklist"]["requirements"][0]["expected"] == "football"


def test_native_select_keeps_requested_option_outside_default_option_window():
    values = payload(
        [
            {
                "id": "0:0",
                "tag": "SELECT",
                "label": "Quantity",
                "value": "1",
                "options": [{"value": str(index), "label": str(index)} for index in range(1, 50)],
            }
        ],
        requirements=[
            {
                "field": "quantity",
                "expected": "35",
                "application": "form",
                "status": "pending",
                "control_id": "0:0",
            },
        ],
    )
    result = build_navigation_context(values)
    assert {"1", "35"} <= {option["value"] for option in all_controls(result)[0]["options"]}


def test_required_cross_frame_ids_keep_frame_identity_without_remapping():
    values = payload(
        [{"id": "0:0", "tag": "BUTTON", "label": "Search"}],
        requirements=[
            {
                "field": "quantity",
                "expected": "4",
                "application": "form",
                "status": "pending",
                "control_id": "1:0",
                "evidence": "Long source evidence " * 200,
            },
        ],
    )
    values["observation"]["frames"].append(
        {
            "url": "https://example.org/widget",
            "text": "Quantity widget",
            "controls": [
                {"id": "1:0", "tag": "INPUT", "type": "number", "label": "Quantity", "value": "1"}
            ],
        }
    )
    result = build_navigation_context(values)
    assert result["task_checklist"]["requirements"][0]["control_id"] == "1:0"
    frame = result["observation"]["frames"][1]
    assert frame["frame_index"] == 1
    assert frame["controls"][0]["id"] == "1:0"
    assert "evidence" not in result["task_checklist"]["requirements"][0]
    assert len(result["task_checklist"]["requirements"][0]["reason"]) <= 140


def test_fresh_context_never_reuses_a_stale_control_identifier():
    values = payload([{"id": "0:new", "tag": "INPUT", "label": "Destination"}])
    values["recent_actions"] = [{"action": "fill", "control_id": "0:old", "status": "done"}]
    values["last_transition"]["changed_controls"] = [{"id": "0:old"}]
    result = build_navigation_context(values)
    assert [item["id"] for item in all_controls(result)] == ["0:new"]
    assert "0:old" not in json.dumps(result)


def test_oversized_task_is_explicitly_rejected_not_silently_shortened():
    values = payload([])
    values["task"] = "User requested literal constraint. " * 600
    with pytest.raises(ValueError, match="no instructions were silently truncated"):
        build_navigation_context(values)


@pytest.mark.parametrize(
    "previous_failure",
    [None, {}, {"decision_valid": True, "response_status": "completed"}],
)
def test_cleared_failure_remains_explicit_null_in_navigation_context(previous_failure):
    values = payload([])
    values["previous_decision_failure"] = previous_failure
    result = build_navigation_context(values)
    assert "previous_decision_failure" in result
    assert result["previous_decision_failure"] is None
    assert json.loads(json.dumps(result))["previous_decision_failure"] is None


def test_failure_feedback_is_compact_then_clears_after_success():
    values = payload([])
    values["previous_decision_failure"] = {
        "error_code": "output_limit",
        "call": 1,
        "decision_valid": False,
        "response_status": "incomplete",
        "provider_text": "Must not become model feedback",
    }
    original = copy.deepcopy(values)
    failed = build_navigation_context(values)
    assert failed["previous_decision_failure"] == {
        "error_code": "output_limit",
        "call": 1,
        "decision_valid": False,
        "response_status": "incomplete",
    }
    assert values == original
    values["previous_decision_failure"] = None
    assert build_navigation_context(values)["previous_decision_failure"] is None


def test_small_whole_context_budget_remains_bounded_with_long_action_history():
    values = payload(
        [
            {"id": f"0:{index}", "tag": "BUTTON", "label": "Background button " * 30}
            for index in range(100)
        ]
    )
    result = build_navigation_context(values, max_chars=5000, observation_chars=3000)
    assert size(result) <= 5000
    assert size(result["observation"]) <= 3000
    assert result["task"] == values["task"]


def test_known_dom_fields_and_recognized_counters_do_not_need_images_every_turn():
    observation = payload(
        [
            {"id": "0:0", "tag": "INPUT", "label": "Destination", "value": "New York"},
            {
                "id": "0:1",
                "tag": "BUTTON",
                "label": "increase Adults",
                "counter": {
                    "label": "Adults",
                    "value": 2,
                    "direction": "increase",
                    "method": "button",
                },
            },
        ]
    )["observation"]
    choice = screenshot_selection(observation, decision_index=0)
    assert not choice["send"]
    assert choice["reason"] == "dom_sufficient"
    observation["frames"][0]["controls"][0]["value"] = "Boston"
    assert not screenshot_selection(observation, decision_index=5)["send"]


def test_ambiguous_counter_gets_one_optional_image_not_repeated_identical_images():
    observation = payload(
        [
            {
                "id": "0:0",
                "tag": "BUTTON",
                "label": "Adults",
                "counter": {"label": "Adults", "value": 2, "direction": "", "method": "button"},
            },
        ]
    )["observation"]
    baseline = copy.deepcopy(observation)
    choice = screenshot_selection(observation, decision_index=3)
    assert choice["send"]
    assert choice["reason"] == "ambiguous_controls"
    later = screenshot_selection(
        observation, previous_fingerprints={choice["fingerprint"]}, decision_index=4
    )
    assert not later["send"]
    assert later["reason"] == "unchanged"
    assert observation == baseline
    assert "image" not in choice


def test_stalled_action_can_request_fresh_image_without_changing_dom_evidence():
    observation = payload([{"id": "0:0", "tag": "INPUT", "label": "Destination"}])["observation"]
    choice = screenshot_selection(
        observation, transition={"status": "no_observable_change"}, decision_index=4
    )
    assert choice["send"]
    assert choice["reason"] == "no_progress"


def test_changed_widget_layout_or_viewport_does_not_reuse_image_fingerprint():
    observation = payload(
        [
            {
                "id": "0:0",
                "tag": "BUTTON",
                "label": "",
                "haspopup": "dialog",
                "rect": {"x": 20, "y": 30, "width": 30, "height": 20},
            }
        ]
    )["observation"]
    first = screenshot_selection(observation)
    seen = {first["fingerprint"]}
    observation["frames"][0]["controls"][0]["rect"]["y"] = 150
    moved = screenshot_selection(observation, previous_fingerprints=seen, decision_index=1)
    assert moved["send"] and moved["fingerprint"] != first["fingerprint"]
    observation["frames"][0]["widgets"] = [{"role": "dialog", "label": "New options"}]
    widget = screenshot_selection(observation, previous_fingerprints=seen, decision_index=2)
    assert widget["send"] and widget["fingerprint"] != moved["fingerprint"]


def test_first_unknown_layout_can_get_an_image_but_mfa_never_does():
    observation = payload([{"id": "0:0", "tag": "A", "label": "Research topic"}])["observation"]
    assert screenshot_selection(observation, decision_index=0)["send"]
    assert not screenshot_selection(observation, decision_index=1)["send"]
    observation["frames"][0]["password_or_code_visible"] = True
    assert screenshot_selection(observation, decision_index=0)["reason"] == "authentication_visible"
    assert not screenshot_selection(observation, decision_index=0)["send"]


def test_control_affordances_distinguish_native_select_and_custom_suggestions():
    values = payload(
        [
            {
                "id": "0:native",
                "tag": "SELECT",
                "label": "Rooms",
                "value": "1",
                "options": [{"value": "1", "label": "1"}, {"value": "2", "label": "2"}],
            },
            {
                "id": "0:combo",
                "tag": "INPUT",
                "role": "combobox",
                "label": "Destination",
                "selection_required": True,
                "value": "New York",
            },
            {"id": "0:option", "tag": "BUTTON", "role": "option", "label": "New York"},
            {
                "id": "0:date",
                "tag": "SPAN",
                "role": "checkbox",
                "label": "Thursday, October 29, 2026",
                "date": "2026-10-29",
            },
            {"id": "0:text", "tag": "INPUT", "type": "text", "label": "City"},
            {"id": "0:check", "tag": "INPUT", "type": "checkbox", "label": "Pool"},
            {"id": "0:disabled", "tag": "BUTTON", "label": "Decrease", "enabled": False},
        ]
    )
    selected = {item["id"]: item for item in all_controls(build_navigation_context(values))}
    assert selected["0:native"]["supported_actions"] == ["select"]
    assert "exact enabled option" in selected["0:native"]["action_hint"]
    assert "fill" in selected["0:combo"]["supported_actions"]
    assert "select" not in selected["0:combo"]["supported_actions"]
    assert selected["0:option"]["supported_actions"] == ["click"]
    assert selected["0:date"]["supported_actions"] == ["click"]
    assert "no focus click" in selected["0:text"]["action_hint"]
    assert "check" in selected["0:check"]["supported_actions"]
    assert not selected["0:disabled"]["supported_actions"]


def test_readonly_calendar_value_can_open_widget_without_claiming_editability():
    values = payload(
        [{"id": "0:date", "tag": "INPUT", "type": "text", "label": "Check-in", "readonly": True}]
    )
    control = all_controls(build_navigation_context(values))[0]
    assert control["supported_actions"] == ["click"]
    assert "no fill" in control["action_hint"]


def test_async_suggestions_pending_does_not_offer_an_old_choice_as_the_next_action():
    values = payload(
        [
            {
                "id": "0:field",
                "tag": "INPUT",
                "role": "combobox",
                "label": "Destination",
                "value": "New York",
                "selection_required": True,
                "suggestions_pending": True,
                "option_ids": ["0:old"],
            },
            {"id": "0:old", "tag": "BUTTON", "role": "option", "label": "Charlotte"},
        ],
        requirements=[
            {
                "field": "destination",
                "expected": "New York",
                "status": "pending",
                "application": "form",
                "next_action": "select_option",
                "control_id": "0:field",
            }
        ],
    )
    result = build_navigation_context(values)
    assert result["interaction_focus"]["phase"] == "wait_suggestions"
    assert result["interaction_focus"]["control_ids"] == ["0:field"]
    field = next(item for item in all_controls(result) if item["id"] == "0:field")
    assert field["suggestions_pending"]


def occupancy_focus_values(adults_status="pending", rooms_status="pending"):
    controls = [
        {
            "id": "0:adult",
            "tag": "BUTTON",
            "label": "increase Adults",
            "counter": {"label": "Adults", "value": 2, "direction": "increase", "method": "button"},
        },
        {
            "id": "0:room",
            "tag": "BUTTON",
            "label": "increase Rooms",
            "counter": {"label": "Rooms", "value": 1, "direction": "increase", "method": "button"},
        },
        {"id": "0:done", "tag": "BUTTON", "label": "Done"},
    ]
    values = payload(
        controls,
        requirements=[
            {
                "field": "adults",
                "expected": "3",
                "application": "form",
                "status": adults_status,
                "counter_controls": [{"control_id": "0:adult"}],
            },
            {
                "field": "rooms",
                "expected": "2",
                "application": "form",
                "status": rooms_status,
                "counter_controls": [{"control_id": "0:room"}],
            },
        ],
    )
    return values


def test_interaction_focus_finishes_visible_rows_before_switching_or_closing():
    values = occupancy_focus_values()
    result = build_navigation_context(values)
    focus = result["interaction_focus"]
    assert focus["phase"] == "set_counters"
    assert focus["fields"] == ["adults", "rooms"]
    assert set(focus["control_ids"]) == {"0:adult", "0:room"}
    assert "before closing/switching" in focus["hint"]
    counter = next(item for item in all_controls(result) if item["id"] == "0:adult")
    assert counter["supported_actions"] == ["set_counter"]
    assert "absolute count" in counter["action_hint"]
    values["task_checklist"]["requirements"][0]["status"] = "verified"
    focus = build_navigation_context(values)["interaction_focus"]
    assert focus["phase"] == "set_counters"
    assert focus["fields"] == ["rooms"]
    assert focus["control_ids"] == ["0:room"]


def test_matching_visible_counters_offer_one_same_frame_confirmation():
    values = occupancy_focus_values("verified", "verified")
    values["observation"]["frames"].append(
        {
            "url": "https://example.org/other",
            "controls": [
                {"id": "1:unrelated", "tag": "BUTTON", "label": "Done"},
            ],
        }
    )
    focus = build_navigation_context(values)["interaction_focus"]
    assert focus["phase"] == "confirm_widget"
    assert focus["control_ids"] == ["0:done"]
    assert "once" in focus["hint"]
    assert "Guidance only" in focus["hint"]


def test_verified_permanent_counter_does_not_invent_a_confirmation_widget():
    values = occupancy_focus_values("verified", "verified")
    values["observation"]["frames"][0]["controls"].pop()
    focus = build_navigation_context(values)["interaction_focus"]
    assert focus["phase"] == "continue"
    assert not focus["control_ids"]


def test_open_calendar_focus_uses_fresh_check_in_before_check_out():
    values = payload(
        [
            {"id": "0:in", "tag": "SPAN", "role": "checkbox", "date": "2026-10-29"},
            {"id": "0:out", "tag": "SPAN", "role": "checkbox", "date": "2026-10-30"},
        ],
        dates=[
            {"field": "check_out", "date": "2026-10-30", "control_id": "0:out"},
            {"field": "check_in", "date": "2026-10-29", "control_id": "0:in"},
        ],
    )
    focus = build_navigation_context(values)["interaction_focus"]
    assert focus["phase"] == "set_dates"
    assert focus["fields"] == ["check_in"]
    assert focus["control_ids"] == ["0:in"]
    values["task_checklist"]["visible_date_choices"].pop()
    assert build_navigation_context(values)["interaction_focus"]["fields"] == ["check_out"]


def test_typed_autocomplete_focus_commits_owned_option_not_refill_or_old_history():
    values = payload(
        [
            {
                "id": "0:field",
                "tag": "INPUT",
                "role": "combobox",
                "label": "Destination",
                "value": "New York",
                "expanded": "true",
                "selection_required": True,
                "option_ids": ["0:city"],
            },
            {
                "id": "0:city",
                "tag": "BUTTON",
                "role": "option",
                "label": "New York",
                "option_primary": "New York",
            },
        ],
        requirements=[
            {
                "field": "destination",
                "expected": "New York",
                "application": "form",
                "status": "pending",
                "control_id": "0:field",
                "next_action": "select_option",
            },
        ],
    )
    values["recent_actions"] = [{"action": "select", "control_id": "0:stale-option"}]
    result = build_navigation_context(values)
    assert result["interaction_focus"]["phase"] == "choose_option"
    assert result["interaction_focus"]["control_ids"] == ["0:city"]
    assert "0:stale-option" not in json.dumps(result)
    values["task_checklist"]["requirements"][0].update(status="verified", next_action="")
    values["observation"]["frames"][0]["controls"][0].update(
        value="New York, New York, United States of America", expanded="false", option_ids=[]
    )
    focus = build_navigation_context(values)["interaction_focus"]
    assert focus["phase"] == "continue"
    assert "do not refill verified fields" in focus["hint"]


def test_value_free_autocomplete_diagnostics_do_not_increase_model_context():
    values = payload([
        {"id": "0:field", "tag": "INPUT", "role": "combobox", "type": "text",
         "name": "destination", "label": "Destination", "value": "New York",
         "selection_required": True, "expanded": "true", "option_ids": ["0:choice"]},
        {"id": "0:choice", "tag": "LI", "role": "option", "label": "New York",
         "option_primary": "New York"},
    ], requirements=[{
        "field": "destination", "expected": "New York", "application": "form",
        "status": "pending", "control_id": "0:field", "next_action": "select_option",
    }])
    baseline = build_navigation_context(values)
    values["observation"]["frames"][0]["autocomplete_diagnostics"] = {
        "field_count": 1, "visible_listbox_count": 1, "visible_option_count": 1,
        "owned_option_count": 1,
        "fields": [{"control_id": "field", "focused": True, "expanded": "true",
                    "controlled_popup_count": 1, "visible_controlled_popup_count": 1,
                    "owned_option_count": 1, "association": "explicit_aria"}],
    }
    assert build_navigation_context(values) == baseline
    assert baseline["interaction_focus"]["phase"] == "choose_option"
    assert baseline["interaction_focus"]["control_ids"] == ["0:choice"]


@pytest.mark.parametrize("next_action", ["open_suggestions", "wait_suggestions"])
def test_qualified_destination_readback_does_not_override_selection_guidance(next_action):
    values = payload(
        [{"id": "0:field", "tag": "INPUT", "role": "combobox", "type": "text",
          "label": "Destination", "value": "New York, New York, United States of America",
          "selection_required": True, "expanded": "false", "option_ids": []}],
        requirements=[{
            "field": "destination", "expected": "New York", "application": "form",
            "status": "pending", "control_id": "0:field", "next_action": next_action,
        }],
    )
    assert build_navigation_context(values)["interaction_focus"]["phase"] == next_action


def test_actual_destination_mismatch_still_requests_the_known_literal_value():
    values = payload(
        [{"id": "0:field", "tag": "INPUT", "role": "combobox", "type": "text",
          "label": "Destination", "value": "Boston", "selection_required": True}],
        requirements=[{
            "field": "destination", "expected": "New York", "application": "form",
            "status": "mismatch", "control_id": "0:field", "next_action": "fill",
        }],
    )
    assert build_navigation_context(values)["interaction_focus"]["phase"] == "fill_fields"


def ready_search_values(*extra):
    controls = [
        {
            "id": "0:city",
            "tag": "INPUT",
            "label": "Destination",
            "value": "New York",
            "form_scope": "0:hotel-search",
        },
        *extra,
        {
            "id": "0:submit",
            "tag": "BUTTON",
            "type": "submit",
            "label": "Search",
            "submits_form": True,
            "form_scope": "0:hotel-search",
        },
    ]
    return payload(
        controls,
        pending=[],
        requirements=[
            {
                "field": "destination",
                "expected": "New York",
                "application": "form",
                "status": "verified",
                "control_id": "0:city",
            },
            {"field": "adults", "expected": "3", "application": "form", "status": "verified"},
            {"field": "rooms", "expected": "2", "application": "form", "status": "verified"},
        ],
    )


def test_prepared_form_keeps_actual_submit_ahead_of_catalogue_links():
    links = [
        {
            "id": f"0:catalogue-{index}",
            "tag": "A",
            "label": "New York hotels",
            "href": f"https://example.org/city/new-york-{index}",
        }
        for index in range(100)
    ]
    values = ready_search_values(*links)
    baseline = copy.deepcopy(values)
    result = build_navigation_context(values)
    controls = {item["id"]: item for item in all_controls(result)}
    assert "0:submit" in controls
    assert controls["0:submit"]["form_scope"] == "0:hotel-search"
    assert result["interaction_focus"]["phase"] == "submit_search"
    assert result["interaction_focus"]["control_ids"] == ["0:submit"]
    assert not any(cid.startswith("0:catalogue") for cid in controls)
    assert result["observation"]["context_coverage"]["requested_controls_omitted"] == 0
    assert result["previous_decision_failure"] is None
    assert size(result) <= 14000
    assert size(result["observation"]) <= 8000
    assert values == baseline


def test_ambiguous_actual_submits_are_not_invented_as_one_prepared_action():
    values = ready_search_values(
        {
            "id": "0:second",
            "tag": "BUTTON",
            "type": "submit",
            "label": "Search",
            "submits_form": True,
            "form_scope": "0:hotel-search",
        }
    )
    focus = build_navigation_context(values)["interaction_focus"]
    assert focus["phase"] == "continue"
    assert not focus["control_ids"]


def test_prepared_search_ignores_other_form_and_anchor_even_if_label_is_search():
    values = ready_search_values(
        {
            "id": "0:newsletter",
            "tag": "BUTTON",
            "type": "submit",
            "label": "Search",
            "form_scope": "0:other-form",
            "submits_form": True,
        },
        {
            "id": "0:catalogue",
            "tag": "A",
            "role": "button",
            "label": "Search",
            "href": "https://example.org/city/new-york",
        },
    )
    assert build_navigation_context(values)["interaction_focus"]["control_ids"] == ["0:submit"]
    values["task_checklist"]["submission_candidates"] = [{"control_id": "0:catalogue"}]
    assert build_navigation_context(values)["interaction_focus"]["phase"] == "continue"


def test_pending_search_response_focus_does_not_repeat_submit_or_return_to_fields():
    values = ready_search_values()
    values["task_checklist"]["search_response_pending"] = True
    values["task_checklist"]["search_transition"] = {
        "status": "pending",
        "method": "observed_search",
        "source_url": "https://example.org/",
        "private_dom_text": "Must not be duplicated in the compact ledger",
    }
    result = build_navigation_context(values)
    assert result["interaction_focus"]["phase"] == "awaiting_results"
    assert not result["interaction_focus"]["control_ids"]
    assert "Do not submit/navigate again" in result["interaction_focus"]["hint"]
    assert result["task_checklist"]["search_transition"]["status"] == "pending"
    assert "private_dom_text" not in result["task_checklist"]["search_transition"]


def test_ledger_candidate_and_transition_contract_keep_only_fresh_search_metadata():
    values = ready_search_values()
    values["task_checklist"].update(
        submission_candidates=[
            {"control_id": "0:submit", "form_scope": "0:hotel-search", "label": "Search"}
        ],
        search_transition={
            "attempted": True,
            "confirmed": False,
            "result_document_id": None,
            "scope": "form_values_and_submission_only",
            "raw_source": "not sent",
        },
        collection_mode="listing_results",
    )
    result = build_navigation_context(values)
    assert result["interaction_focus"]["control_ids"] == ["0:submit"]
    assert result["task_checklist"]["search_transition"] == {
        "attempted": True,
        "confirmed": False,
        "result_document_id": None,
        "scope": "form_values_and_submission_only",
    }
    assert result["task_checklist"]["collection_mode"] == "listing_results"


def test_confirmed_search_focus_collects_results_without_reopening_prepared_form():
    values = ready_search_values()
    values["task_checklist"]["search_submitted"] = True
    focus = build_navigation_context(values)["interaction_focus"]
    assert focus["phase"] == "collect_results"
    assert not focus["control_ids"]
    assert "Do not refill" in focus["hint"]
    values["task_checklist"]["requirements"][0]["status"] = "pending"
    values["task_checklist"]["pending_fields"] = ["destination"]
    assert build_navigation_context(values)["interaction_focus"]["phase"] == "continue"


def test_confirmed_search_with_linked_detail_request_does_not_end_collection():
    values = ready_search_values()
    values["task_checklist"].update(search_submitted=True, collection_mode="linked_details")
    focus = build_navigation_context(values)["interaction_focus"]
    assert focus["phase"] == "collect_results"
    assert "continue collecting requested linked pages" in focus["hint"]


def test_unverified_form_and_explicit_no_candidate_flag_never_authorize_submission():
    values = ready_search_values()
    values["task_checklist"]["requirements"][0]["status"] = "pending"
    values["task_checklist"]["pending_fields"] = ["destination"]
    assert build_navigation_context(values)["interaction_focus"]["phase"] == "continue"
    values["task_checklist"]["requirements"][0]["status"] = "verified"
    values["task_checklist"]["pending_fields"] = []
    values["task_checklist"]["submission_candidates"] = []
    assert build_navigation_context(values)["interaction_focus"]["phase"] == "continue"
    values["task_checklist"]["submission_candidates"] = [{"control_id": "0:submit"}]
    values["task_checklist"]["submission_ready"] = False
    assert build_navigation_context(values)["interaction_focus"]["phase"] == "continue"


def test_generic_news_navigation_retains_links_without_inventing_prepared_search():
    values = payload(
        [
            {
                "id": "0:sport",
                "tag": "A",
                "label": "Sports headlines",
                "href": "https://example.org/sports",
            },
        ],
        pending=[],
        requirements=[],
    )
    values["task"] = "Get relevant sports reports."
    result = build_navigation_context(values)
    assert result["interaction_focus"]["phase"] == "continue"
    assert all_controls(result)[0]["href"] == "https://example.org/sports"
    assert all_controls(result)[0]["supported_actions"] == ["click"]


def destination_context(value, action, *, expanded="false", options=(), known=True):
    field = {
        "id": "0:field",
        "tag": "INPUT",
        "role": "combobox",
        "name": "destination",
        "label": "Enter destination",
        "selection_required": True,
        "expanded": expanded,
        "option_ids": [item["id"] for item in options],
        "rect": {"x": 10, "y": 20, "width": 200, "height": 40},
    }
    if known:
        field["value"] = value
    check = {
        "field": "destination",
        "expected": "New York",
        "application": "form",
        "status": "pending",
        "control_id": "0:field",
        "observed": value if known else None,
    }
    if action:
        check["next_action"] = action
    values = payload([field, *options], pending=["destination"], requirements=[check])
    values["observation"]["frames"][0]["viewport"] = {
        "width": 1280,
        "height": 720,
        "scroll_y": 0,
    }
    return values


@pytest.mark.parametrize("value", ["", "Boston"])
def test_blank_or_wrong_destination_focus_fills_directly_with_explicit_current_value(value):
    values = destination_context(value, "fill")
    baseline = copy.deepcopy(values)
    result = build_navigation_context(values)
    assert result["interaction_focus"]["phase"] == "fill_fields"
    assert result["interaction_focus"]["control_ids"] == ["0:field"]
    assert result["task_checklist"]["requirements"][0]["observed"] == value
    assert all_controls(result)[0]["value"] == value
    assert "fill" in all_controls(result)[0]["supported_actions"]
    assert "no focus click" in all_controls(result)[0]["action_hint"].casefold()
    assert result["context_metrics"]["tier"] == "focused"
    assert size(result) <= 6500 and size(result["observation"]) <= 3500
    assert values == baseline


def test_missing_destination_value_is_unknown_not_an_invented_blank_or_fill_step():
    values = destination_context(None, None, known=False)
    result = build_navigation_context(values)
    assert result["task_checklist"]["requirements"][0]["observed"] is None
    field = next(item for item in all_controls(result) if item["id"] == "0:field")
    assert "value" not in field
    assert result["interaction_focus"]["phase"] == "continue"


def test_matching_typed_destination_opens_once_then_waits_if_owned_options_absent():
    values = destination_context("New York", "open_suggestions")
    result = build_navigation_context(values)
    assert result["interaction_focus"]["phase"] == "open_suggestions"
    assert result["interaction_focus"]["control_ids"] == ["0:field"]
    values["observation"]["frames"][0]["controls"][0]["expanded"] = "true"
    values["task_checklist"]["requirements"][0]["next_action"] = "wait_suggestions"
    result = build_navigation_context(values)
    assert result["interaction_focus"]["phase"] == "wait_suggestions"
    assert "wait/inspect" in result["interaction_focus"]["hint"]


def test_fresh_owned_options_are_preserved_but_successful_click_waits_for_committed_readback():
    option = {
        "id": "0:choice",
        "tag": "BUTTON",
        "role": "option",
        "option_primary": "New York",
        "label": "New York",
        "text": "New York, United States of America",
    }
    values = destination_context("New York", "select_option", expanded="true", options=[option])
    result = build_navigation_context(values)
    assert result["interaction_focus"]["phase"] == "choose_option"
    assert result["interaction_focus"]["control_ids"] == ["0:choice"]
    found = next(item for item in all_controls(result) if item["id"] == "0:choice")
    assert found["text"] == option["text"]
    assert found["supported_actions"] == ["click"]
    values["task_checklist"]["requirements"][0]["next_action"] = "wait_suggestions"
    assert build_navigation_context(values)["interaction_focus"]["phase"] == "wait_suggestions"


def test_focused_navigation_drops_geometry_and_background_but_keeps_it_for_an_actual_image():
    values = destination_context("", "fill")
    values["observation"]["frames"][0]["text"] = "Duplicated parent/page text " * 200
    values["observation"]["frames"][0]["controls"].extend(
        [
            {
                "id": f"0:bg-{index}",
                "tag": "A",
                "label": "Catalogue link",
                "href": f"https://example.org/catalogue/{index}",
                "context": "Duplicate " * 40,
            }
            for index in range(120)
        ]
    )
    result = build_navigation_context(values)
    assert [item["id"] for item in all_controls(result)] == ["0:field"]
    assert "rect" not in all_controls(result)[0]
    assert "viewport" not in result["observation"]["frames"][0]
    assert result["observation"]["frames"][0]["text"] == ""
    visual = build_navigation_context(values, include_geometry=True)
    assert (
        all_controls(visual)[0]["rect"] == values["observation"]["frames"][0]["controls"][0]["rect"]
    )
    assert (
        visual["observation"]["frames"][0]["viewport"]
        == values["observation"]["frames"][0]["viewport"]
    )


def test_large_original_request_uses_rich_budget_without_truncating_required_values():
    values = destination_context("", "fill")
    values["task"] += " Preserve this user-specified output detail." * 125
    result = build_navigation_context(values)
    assert result["context_metrics"]["tier"] == "rich_fallback"
    assert result["task"] == values["task"]
    assert result["task_checklist"]["requirements"][0]["expected"] == "New York"
    assert size(result) <= 14000 and size(result["observation"]) <= 8000


def test_rich_browsing_still_keeps_generic_links_page_text_and_default_geometry():
    values = payload(
        [
            {
                "id": "0:science",
                "tag": "A",
                "label": "Research update",
                "href": "https://example.org/research",
                "rect": {"x": 0, "y": 10, "width": 200, "height": 20},
            },
        ],
        pending=[],
        requirements=[],
        text="Scientific research index content",
    )
    values["task"] = "Find scientific research and open related detail pages."
    result = build_navigation_context(values)
    assert result["context_metrics"]["tier"] == "rich"
    assert all_controls(result)[0]["href"] == "https://example.org/research"
    assert "rect" in all_controls(result)[0]
    assert result["observation"]["frames"][0]["text"] == values["observation"]["frames"][0]["text"]


def test_large_owned_option_inventory_falls_back_without_erasing_choice_ambiguity():
    options = [
        {
            "id": f"0:choice-{index}",
            "tag": "BUTTON",
            "role": "option",
            "option_primary": "New York",
            "label": "New York " + f"Qualifier {index} " * 15,
            "text": "New York " + f"Different observed option subtitle {index}. " * 5,
        }
        for index in range(12)
    ]
    values = destination_context("New York", "select_option", expanded="true", options=options)
    result = build_navigation_context(values)
    assert result["context_metrics"]["tier"] == "rich_fallback"
    ids = {item["id"] for item in all_controls(result)}
    assert {item["id"] for item in options} | {"0:field"} <= ids
    field = next(item for item in all_controls(result) if item["id"] == "0:field")
    assert set(field["option_ids"]) == {item["id"] for item in options}
    assert result["observation"]["context_coverage"]["associated_options_omitted"] == 0
    assert size(result) <= 14000 and size(result["observation"]) <= 8000


def test_focused_view_keeps_nonduplicate_form_button_readback_text():
    values = destination_context("", "fill")
    values["observation"]["frames"][0]["controls"].extend(
        [
            {
                "id": "0:dates",
                "tag": "BUTTON",
                "label": "Select dates",
                "text": "Thu, Oct 29 — Fri, Oct 30",
            },
            {
                "id": "0:guests",
                "tag": "BUTTON",
                "label": "Number of travelers and rooms",
                "text": "3 adults · 0 children · 2 rooms",
            },
        ]
    )
    result = build_navigation_context(values)
    found = {item["id"]: item for item in all_controls(result)}
    assert found["0:dates"]["text"] == "Thu, Oct 29 — Fri, Oct 30"
    assert found["0:guests"]["text"] == "3 adults · 0 children · 2 rooms"


@pytest.mark.parametrize(
    "native",
    [
        {"tag": "BUTTON", "type": "submit", "submits_form": True},
        {"tag": "BUTTON", "type": "submit"},
        {"tag": "INPUT", "type": "image", "submits_form": True},
    ],
)
def test_focused_form_retains_generic_native_submit_without_claiming_search_readiness(native):
    values = destination_context("", "fill")
    values["task_checklist"]["submission_candidates"] = []
    submit = {"id": "0:submit", "label": "Continue", "form_scope": "0:form:0", **native}
    values["observation"]["frames"][0]["controls"].append(submit)
    original = copy.deepcopy(values)
    result = build_navigation_context(values)
    found = {item["id"]: item for item in all_controls(result)}
    assert found["0:submit"]["type"] == native["type"]
    assert found["0:submit"]["supported_actions"] == ["click"]
    if native.get("submits_form"):
        assert found["0:submit"]["submits_form"]
    assert result["interaction_focus"]["phase"] == "fill_fields"
    assert result["interaction_focus"]["control_ids"] == ["0:field"]
    assert result["task_checklist"]["pending_fields"] == ["destination"]
    assert not result["task_checklist"]["search_submitted"]
    assert result["context_metrics"]["tier"] == "focused"
    assert size(result) <= 6500 and values == original
