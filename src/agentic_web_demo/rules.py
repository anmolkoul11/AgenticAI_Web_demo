"""Explicit, deterministic business rules; YAML never contains executable code."""

import hashlib
import json
from decimal import Decimal
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from agentic_web_demo.listings import Listing


class Rules(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    rule_id: str = Field(default="affordable-quality-stay", pattern=r"^[a-z0-9-]{1,64}$")
    version: int = Field(default=1, ge=1, strict=True)
    max_price: Decimal = Field(default=Decimal("200"), ge=0, allow_inf_nan=False)
    min_rating: Decimal = Field(default=Decimal("4"), ge=0, le=5, allow_inf_nan=False)
    currency: Literal["USD"] = "USD"
    rating_scale: Literal[5] = 5
    price_basis: Literal["per_night_taxes_included"] = "per_night_taxes_included"

    def fingerprint(self) -> str:
        payload = self.model_dump(mode="json")
        payload["max_price"] = str(self.max_price.normalize())
        payload["min_rating"] = str(self.min_rating.normalize())
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

    def reasons(self, listing: Listing) -> list[str]:
        reasons = []
        if listing.currency != self.currency or listing.price_basis != self.price_basis:
            reasons.append("incompatible_price_basis_or_currency")
        if listing.rating_scale != self.rating_scale:
            reasons.append("incompatible_rating_scale")
        if listing.price > self.max_price:
            reasons.append("price_above_maximum")
        if listing.rating < self.min_rating:
            reasons.append("rating_below_minimum")
        return reasons


def load_rules(path: Path | None = None) -> Rules:
    if path is None:
        return Rules()
    if path.stat().st_size > 16_384:
        raise ValueError("Rules file exceeds the demo size limit")
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Rules must be a YAML mapping")
    return Rules.model_validate(payload)
