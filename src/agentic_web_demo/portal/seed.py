"""Fictional, deterministic records. No external website data or live inventory."""

from dataclasses import dataclass


@dataclass(frozen=True)
class DemoListing:
    id: str
    title: str
    city: str
    price: int
    rating: str


LISTINGS = (
    DemoListing("NYC-001", "Harbor House", "New York", 180, "4.6"),
    DemoListing("NYC-002", "Parkside Suites", "New York", 240, "4.8"),
    DemoListing("NYC-003", "Midtown Budget Inn", "New York", 120, "3.7"),
    DemoListing("NYC-004", "East River Lodge", "New York", 200, "4.0"),
    DemoListing("BOS-001", "Beacon Court", "Boston", 165, "4.3"),
    DemoListing("BOS-002", "Seaport Studio", "Boston", 220, "4.7"),
)
