"""Domain-neutral browser state, control bindings and action-effect feedback.

The model interprets the request; these helpers only describe observed controls
and changes. No site selectors, topic classifiers or model-asserted verification.
"""

import hashlib
import json


def controls(observation):
    return [c for frame in observation.get("frames", []) for c in frame.get("controls", [])]


def identity(control):
    return {
        # Normalized interaction-state entries carry frame, not an ephemeral ID.
        # Preserve it when comparing those entries with fresh raw controls.
        "frame": str(control["id"]).split(":", 1)[0]
        if control.get("id")
        else control.get("frame", ""),
        **{key: control.get(key, "") for key in ("tag", "role", "type", "name", "label")},
    }


def bound_controls(binding, observation):
    if binding["document"] != observation.get("document_id", observation.get("url")):
        return []
    exact = [c for c in controls(observation) if identity(c) == binding["identity"]]
    if exact:
        return exact
    # A rerender can change a field's accessible label. A unique native name
    # remains useful; unnamed/ambiguous controls are never guessed.
    wanted = binding["identity"]
    if not wanted["name"]:
        return []
    return [
        c
        for c in controls(observation)
        if all(identity(c)[key] == wanted[key] for key in ("frame", "tag", "type", "name"))
    ]


def interaction_state(observation):
    """Ignore body/ad text, but retain widget state, values and the viewport."""
    items = []
    for control in controls(observation):
        if control.get("tag") == "A" and control.get("role") not in {"button", "option"}:
            continue
        items.append(
            {
                **identity(control),
                **{
                    key: control.get(key)
                    for key in ("value", "selected", "expanded", "enabled", "counter", "date")
                },
            }
        )
    items.sort(key=lambda c: json.dumps(c, sort_keys=True))
    return {
        "document": observation.get("document_id", observation.get("url")),
        "controls": items,
        "widgets": [f.get("widgets", []) for f in observation.get("frames", [])],
        "scroll": [f.get("viewport", {}).get("scroll_y") for f in observation.get("frames", [])],
    }


def state_fingerprint(observation):
    return hashlib.sha256(
        json.dumps(interaction_state(observation), sort_keys=True).encode()
    ).hexdigest()


def transition(before, after):
    old, new = interaction_state(before), interaction_state(after)
    old_items = {json.dumps(identity(c), sort_keys=True): c for c in old["controls"]}
    new_items = {json.dumps(identity(c), sort_keys=True): c for c in new["controls"]}
    changed = [
        {
            "control": c["label"] or c["name"],
            "before": old_items[key].get("value"),
            "after": c.get("value"),
            "selected": c.get("selected"),
            "counter": c.get("counter"),
            "expanded": c.get("expanded"),
        }
        for key, c in new_items.items()
        if key in old_items and c != old_items[key]
    ]
    added = [
        c
        for c in controls(after)
        if json.dumps(identity(c), sort_keys=True) not in old_items
        and (c.get("tag") != "A" or c.get("role") in {"option", "button"})
    ]
    document_changed = old["document"] != new["document"]
    widget_changed = old["widgets"] != new["widgets"]
    scrolled = old["scroll"] != new["scroll"]
    removed = len(old_items.keys() - new_items.keys())
    observed = bool(document_changed or widget_changed or scrolled or changed or added or removed)
    return {
        "status": "change_observed" if observed else "no_observable_change",
        "document_changed": document_changed,
        "widget_changed": widget_changed,
        "scrolled": scrolled,
        "changed_controls": changed[:8],
        "new_controls": [
            {
                "id": c.get("id"),
                "label": c.get("label"),
                "role": c.get("role"),
                "counter": c.get("counter"),
            }
            for c in added[:12]
        ],
        "removed_controls": removed,
        "note": "Observed UI change, not proof of request fulfillment or result accuracy."
        if observed
        else "No meaningful control/widget change was observed. Inspect another "
        "control, the open widget, or wait once for delayed rendering; do not repeat blindly.",
    }
