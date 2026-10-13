"""Human-completed authentication checks. Never read code values, inboxes or cookies."""

import re
from urllib.parse import urlsplit

from agentic_web_demo.custom_fetch import WebsiteError, origin

AUTHENTICATION_STATE = """selector => {
    const visible = el => !!el && el.getClientRects().length &&
        getComputedStyle(el).visibility !== 'hidden';
    const count = query => [...document.querySelectorAll(query)].filter(visible).length;
    const text = (document.body?.innerText || '').slice(0, 6000).toLowerCase();
    const emailNotice = /check your (email|inbox)|sent (you )?(an? )?(email|code)/;
    const codeNotice = /enter (the |your )?(verification |security |login )?code/;
    const restricted = ['verify you are human', 'checking your browser', 'access denied',
        'complete the captcha', 'unusual traffic',
        'please enable js and disable any ad blocker'];
    return {
        password_form: count('input[type="password"]') > 0,
        code_form: count('input[autocomplete="one-time-code"],input[name*="otp" i],' +
            'input[name*="verification" i],input[name="code" i],input[id*="otp" i]') > 0,
        email_notice: emailNotice.test(text) || codeNotice.test(text),
        access_restriction: restricted.some(marker => text.includes(marker)),
        success_count: selector ? count(selector) : 0,
        https: location.protocol === 'https:'
    };
}"""


def assess_authentication(page, target_origin, success_selector=""):
    """A return URL alone cannot prove authentication; label operator confirmation honestly."""
    state = page.evaluate(AUTHENTICATION_STATE, success_selector)
    if not state["https"] or origin(page.url) != target_origin:
        raise WebsiteError(
            "Finish verification in the original browser and return to the selected website "
            "before continuing. No extraction call ran."
        )
    if state["access_restriction"]:
        raise WebsiteError(
            "The website is still restricting access. Complete its offered "
            "verification yourself or cancel. No extraction call ran."
        )
    if state["password_form"] or state["code_form"]:
        raise WebsiteError(
            "A password or verification-code form is still visible. "
            "Complete it in the browser before continuing."
        )
    if re.search(
        r"/(?:login|signin|sign-in|verify|verification|otp|callback|authorize)(?:/|$)",
        urlsplit(page.url).path,
        re.I,
    ):
        raise WebsiteError(
            "An authentication page is still open. Complete sign-in and "
            "return to the website before continuing."
        )
    if success_selector:
        if state["success_count"] != 1:
            raise WebsiteError(
                "The configured signed-in indicator is missing or ambiguous. "
                "Check sign-in and the indicator before continuing."
            )
        return {"status": "authenticated", "verified": True, "verification": "visible_indicator"}
    if state["email_notice"]:
        raise WebsiteError(
            "The page still asks for email verification. Complete it in the "
            "browser and return to the website before continuing."
        )
    return {
        "status": "operator_confirmed",
        "verified": False,
        "verification": "operator_attestation",
    }


def authentication_expired(page, target_origin):
    """Detect obvious reauthentication, not every site's session expiry semantics."""
    state = page.evaluate(AUTHENTICATION_STATE, "")
    return (
        not state["https"]
        or origin(page.url) != target_origin
        or state["password_form"]
        or state["code_form"]
        or state["access_restriction"]
        or bool(
            re.search(
                r"/(?:login|signin|sign-in|verify|verification|otp|callback|authorize)(?:/|$)",
                urlsplit(page.url).path,
                re.I,
            )
        )
    )
