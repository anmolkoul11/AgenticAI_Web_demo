"""Explicitly disclosed current-year defaults for user stay requests only.

Do not use this resolver on website text: source dates must retain source evidence.
"""

import re
from datetime import date

from agentic_web_demo.browser_navigation import requested_dates
from agentic_web_demo.custom_fetch import WebsiteError


def resolve_stay_dates(instructions, reference_date=None):
    reference = reference_date or date.today()
    explicit = requested_dates(instructions)
    if explicit or re.search(r"\b\d{4}\b", instructions):
        return explicit, None
    months = (
        "January February March April May June July August September October November December"
    ).split()
    month = "(?:" + "|".join(months + [name[:3] for name in months]) + ")"
    day = r"\d{1,2}(?:st|nd|rd|th)?\b"
    join = r"\s*(?:-|\u2013|\u2014|to|and)\s*"
    pattern = re.compile(
        rf"\b(?:{month}\s+{day}{join}{month}\s+{day}|"
        rf"{month}\s+{day}{join}{day}|{day}{join}{day}\s+{month}|"
        rf"{month}\s+{day}|{day}\s+{month})",
        re.I,
    )
    amended = pattern.sub(lambda match: f"{match[0]} {reference.year}", instructions)
    if amended == instructions:
        return [], None
    resolved = requested_dates(amended)
    if len(resolved) != 2:
        return [], None
    if resolved[0] < reference.isoformat() or resolved[0] >= resolved[1]:
        raise WebsiteError(
            "The dates without a year do not form a current-year stay starting today or later. "
            "Provide explicit check-in and check-out years; no next year was assumed. "
            "Cancel this browser and start a new session with the corrected request."
        )
    return resolved, {
        "policy": "current_year_if_valid",
        "reference_date": reference.isoformat(),
        "year": reference.year,
        "check_in": resolved[0],
        "check_out": resolved[1],
        "guidance": f"Year omitted: using {reference.year}; check-in {resolved[0]}, "
        f"check-out {resolved[1]}. Review these dates before saving results.",
    }
