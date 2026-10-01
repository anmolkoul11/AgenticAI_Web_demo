"""Fictional, deterministic records. No external website data or live inventory."""

from dataclasses import dataclass


@dataclass(frozen=True)
class DemoListing:
    id: str
    title: str
    city: str
    price: int
    rating: str


_ORIGINAL = (
    DemoListing("NYC-001", "Harbor House", "New York", 180, "4.6"),
    DemoListing("NYC-002", "Parkside Suites", "New York", 240, "4.8"),
    DemoListing("NYC-003", "Midtown Budget Inn", "New York", 120, "3.7"),
    DemoListing("NYC-004", "East River Lodge", "New York", 200, "4.0"),
    DemoListing("BOS-001", "Beacon Court", "Boston", 165, "4.3"),
    DemoListing("BOS-002", "Seaport Studio", "Boston", 220, "4.7"),
)

CITIES = (
    ("NYC", "New York"),
    ("BOS", "Boston"),
    ("CHI", "Chicago"),
    ("LAX", "Los Angeles"),
    ("SFO", "San Francisco"),
    ("SEA", "Seattle"),
    ("MIA", "Miami"),
    ("LAS", "Las Vegas"),
    ("WAS", "Washington DC"),
    ("ATL", "Atlanta"),
)
_NAMES = (
    "Garden Court",
    "Skyline Suites",
    "Market Lane Inn",
    "Riverside House",
    "Cedar Terrace",
    "Lantern Lodge",
    "Orchard Place",
    "Summit Retreat",
    "Maple Budget Inn",
    "Grand Promenade",
)
_PRICES = (145, 265, 110, 200, 150, 190, 99, 275, 85, 215)
_RATINGS = ("4.4", "4.8", "3.6", "4.0", "4.2", "4.7", "4.1", "4.9", "3.5", "3.8")

# Preserve the original IDs and values; new records are deterministic and fictional.
LISTINGS = tuple(
    next(
        (item for item in _ORIGINAL if item.id == f"{prefix}-{index + 1:03}"),
        DemoListing(
            f"{prefix}-{index + 1:03}",
            f"{city} {_NAMES[index]}",
            city,
            _PRICES[index],
            _RATINGS[index],
        ),
    )
    for prefix, city in CITIES
    for index in range(10)
)
