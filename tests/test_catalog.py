from collections import Counter
from decimal import Decimal

from agentic_web_demo.portal.seed import CITIES, LISTINGS


def test_catalog_has_ten_cities_and_ten_unique_hotels_each():
    assert len(CITIES) == 10
    assert len(LISTINGS) == 100
    assert len({row.id for row in LISTINGS}) == 100
    assert Counter(row.city for row in LISTINGS) == {city: 10 for _, city in CITIES}
    assert all(row.price > 0 and 0 <= Decimal(row.rating) <= 5 for row in LISTINGS)


def test_new_york_default_rule_matches_five_and_preserves_originals():
    hotels = [row for row in LISTINGS if row.city == "New York"]
    assert {row.id for row in hotels if row.price <= 200 and Decimal(row.rating) >= 4} == {
        "NYC-001",
        "NYC-004",
        "NYC-005",
        "NYC-006",
        "NYC-007",
    }
    assert hotels[0].title == "Harbor House" and hotels[0].price == 180
