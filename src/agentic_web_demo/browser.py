"""Playwright adapter for the authorized local demo portal only."""

import os
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import urlsplit

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import expect, sync_playwright
from pydantic import ValidationError

from agentic_web_demo.listings import Listing, Snapshot, Stay


class ExtractionError(RuntimeError):
    """A safe, user-facing error that never includes browser logs or credentials."""


@dataclass(frozen=True)
class Credentials:
    username: str = field(repr=False)
    password: str = field(repr=False)

    @classmethod
    def from_env(cls):
        username = os.environ.get("DEMO_USERNAME", "demo")
        password = os.environ.get("DEMO_PASSWORD", "")
        if not username.strip() or not password:
            raise ExtractionError("Set DEMO_USERNAME and DEMO_PASSWORD in this terminal.")
        return cls(username, password)


def portal_origin(url: str) -> str:
    """No external targets, URL credentials, paths or query strings in this adapter."""
    parsed = urlsplit(url)
    try:
        port = parsed.port
    except ValueError as exc:
        raise ExtractionError("Invalid local portal port.") from exc
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"localhost", "127.0.0.1"}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or port == 0
    ):
        raise ExtractionError("Use a local portal origin such as http://127.0.0.1:8000.")
    return f"http://{parsed.hostname}" + (f":{port}" if port is not None else "")


def extract_listings(
    stay: Stay,
    credentials: Credentials,
    *,
    base_url: str = "http://127.0.0.1:8000",
    headed: bool = False,
) -> Snapshot:
    origin = portal_origin(base_url)
    stay.require_current_dates()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=not headed)
            try:
                context = browser.new_context(service_workers="block", accept_downloads=False)
                context.set_default_timeout(10_000)
                # Block off-origin subresources and redirects, including during login.
                context.route(
                    "**/*",
                    lambda route: (
                        route.continue_()
                        if route.request.url.startswith(origin + "/")
                        else route.abort()
                    ),
                )
                page = context.new_page()
                response = page.goto(origin + "/login", wait_until="domcontentloaded")
                if response is None or response.status != 200:
                    raise ExtractionError("The local portal login page is unavailable.")
                page.get_by_label("Username", exact=True).fill(credentials.username)
                page.get_by_label("Password", exact=True).fill(credentials.password)
                with page.expect_navigation(wait_until="domcontentloaded"):
                    page.get_by_role("button", name="Sign in", exact=True).click()
                if urlsplit(page.url).path != "/listings":
                    raise ExtractionError("Login failed. Check the dedicated demo credentials.")
                page.get_by_label("City", exact=True).fill(stay.city)
                page.get_by_label("Check-in", exact=True).fill(stay.check_in.isoformat())
                page.get_by_label("Check-out", exact=True).fill(stay.check_out.isoformat())
                with page.expect_navigation(wait_until="domcontentloaded"):
                    page.get_by_role("button", name="Search stays", exact=True).click()
                expect(page.get_by_test_id("result-count")).to_be_visible()
                expect(page.get_by_label("Check-in", exact=True)).to_have_value(
                    stay.check_in.isoformat()
                )
                expect(page.get_by_label("Check-out", exact=True)).to_have_value(
                    stay.check_out.isoformat()
                )
                cards = page.get_by_test_id("listing")
                count = cards.count()
                summary = page.get_by_test_id("result-count").inner_text()
                match = re.match(r"^(\d+) listings", summary)
                if not match or int(match.group(1)) != count:
                    raise ExtractionError("Listing count mismatch; portal markup may have changed.")
                if count == 0:
                    expect(page.get_by_test_id("empty-state")).to_be_visible()
                timestamp = datetime.now(UTC)
                records = []
                for card in cards.all():

                    def value(name, card=card):
                        return card.locator(f'[data-field="{name}"]').inner_text().strip()

                    link = card.locator('[data-field="url"]').get_attribute("href") or ""
                    if not link.startswith(origin + "/listings"):
                        raise ExtractionError("Unexpected listing URL; no records saved.")
                    if value("price_basis") != "Per night, taxes and fees included":
                        raise ExtractionError("Unknown price basis; no records saved.")
                    records.append(
                        Listing(
                            listing_id=value("id"),
                            title=value("title"),
                            city=value("city"),
                            check_in=stay.check_in,
                            check_out=stay.check_out,
                            price=value("price"),
                            currency=value("currency"),
                            rating=value("rating"),
                            rating_scale=int(value("rating_scale")),
                            price_basis="per_night_taxes_included",
                            source_url=link,
                            extracted_at=timestamp,
                        )
                    )
                result = Snapshot(stay=stay, extracted_at=timestamp, listings=tuple(records))
                # Revoke the short-lived authenticated session before closing the context.
                with page.expect_navigation(wait_until="domcontentloaded"):
                    page.get_by_role("button", name="Sign out", exact=True).click()
                return result
            finally:
                browser.close()
    except ExtractionError:
        raise
    except (ValidationError, ValueError) as exc:
        raise ExtractionError("Extracted records failed validation; no records saved.") from exc
    except (PlaywrightError, AssertionError) as exc:
        raise ExtractionError(
            "Browser extraction failed. Check the portal is running, Chromium is installed, "
            "and the page matches this adapter. No records saved."
        ) from exc
