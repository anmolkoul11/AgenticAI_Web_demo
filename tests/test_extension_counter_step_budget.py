"""Source regression scenarios for bounded large occupancy changes; not live sites."""

import pytest

from test_extension_executor_contract import executor_page, observed, shared_local_page


def button_counter(page, before):
    page.set_content(f'''<main><div>Adults
      <button id="decrease" aria-label="Decrease adult count by 1"
        onclick="document.querySelector('output').textContent--">-</button>
      <output>{before}</output>
      <button id="increase" aria-label="Increase adult count by 1"
        onclick="document.querySelector('output').textContent++">+</button>
      </div></main>''')


def payload_for(page, target, direction=None):
    observation = observed(page)
    field = next(item for item in observation["frame"]["controls"]
                 if item.get("counter") and (direction is None or item["counter"]["direction"] == direction))
    return {"document_token": observation["document_token"], "facts": field,
            "decision": {"action": "set_counter", "control_id": field["id"], "value": str(target)}}


def execute(page, payload, native, button_id):
    if not native:
        return page.evaluate("p=>__agenticTabExecutor.dispatch('execute',p)", payload)
    packet = page.evaluate("p=>__agenticTabExecutor.dispatch('native_begin',p)", payload)
    steps = 0
    while packet.get("native_step"):
        step = packet["native_step"]
        continuation = {"document_token": payload["document_token"],
                        "transaction_id": packet["transaction_id"], "step_id": step["id"]}
        page.evaluate("p=>__agenticTabExecutor.dispatch('native_validate',p)", continuation)
        assert step["kind"] == "click"
        # Isolated fixture input only; no actual website or native debugger.
        page.locator("#" + button_id).evaluate("e=>e.click()")
        steps += 1
        assert steps <= 30
        packet = page.evaluate("p=>__agenticTabExecutor.dispatch('native_continue',p)", continuation)
    assert packet["result"]["steps"] == steps
    return packet["result"]


@pytest.mark.parametrize("native", [False, True])
@pytest.mark.parametrize("before,target", [(6, 18), (18, 5), (0, 30)])
def test_large_supported_target_checks_every_step_and_reaches_absolute_count(executor_page, native, before, target):
    page = executor_page
    button_counter(page, before)
    direction = "increase" if target > before else "decrease"
    result = execute(page, payload_for(page, target, direction), native, direction)
    assert result["status"] == "counter_verified"
    assert result["before"] == before and result["expected"] == result["observed"] == target
    assert result["steps"] == result["attempts"] == abs(target - before)
    assert page.locator("output").inner_text() == str(target)


@pytest.mark.parametrize("attributes,target,reason", [
    ('min="1" max="30"', 31, "target_limit"),
    ('min="1" max="10"', 18, "above_maximum"),
    ('min="1" max="30"', 0, "below_minimum"),
    ('min="0" max="30" readonly', 18, "read_only"),
])
def test_counter_guard_returns_structured_no_input_evidence(executor_page, attributes, target, reason):
    page = executor_page
    page.set_content(f'<main><label>Adults<input type="number" value="6" {attributes}></label></main>')
    result = execute(page, payload_for(page, target), False, "")
    assert result["status"] == "counter_unconfirmed"
    assert result["counter_rejection"]["reason"] == reason
    assert result["before"] == result["observed"] == 6 and result["expected"] == target
    assert result["counter_rejection"]["max_steps"] == result["counter_rejection"]["max_target"] == 30
    assert result["steps"] == result["attempts"] == 0 and not result["dispatched"]
    assert result["retryable"] is False
    assert page.locator("input").input_value() == "6"


def test_step_budget_remains_bounded_when_returned_count_exceeds_supported_target_range(executor_page):
    page = executor_page
    button_counter(page, 50)
    result = execute(page, payload_for(page, 3, "decrease"), False, "decrease")
    assert result["counter_rejection"]["reason"] == "step_limit"
    assert result["before"] == result["observed"] == 50 and result["attempts"] == 0


def test_unsupported_semantic_numeric_display_remains_blocked_before_input(executor_page):
    page = executor_page
    page.set_content('<main><div role="spinbutton" aria-label="Adults" aria-valuenow="6" tabindex="0"></div></main>')
    result = execute(page, payload_for(page, 18), False, "")
    assert result["counter_rejection"]["reason"] == "unsupported_numeric_control"
    assert result["attempts"] == 0 and not result["dispatched"]
