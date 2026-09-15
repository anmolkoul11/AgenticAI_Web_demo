"""Validated contracts shared by browser, storage, and future agent tools."""

from datetime import date
from decimal import Decimal
from typing import Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, HttpUrl, model_validator


class Stay(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)
    city: str = Field(default="", max_length=100)
    check_in: date
    check_out: date

    @model_validator(mode="after")
    def ordered_dates(self) -> Self:
        if not 1 <= (self.check_out - self.check_in).days <= 30:
            raise ValueError("Stay must contain 1 to 30 nights")
        return self

    def require_current_dates(self) -> None:
        # Validate at extraction time, not when reloading historical snapshots.
        if self.check_in < date.today():
            raise ValueError("Check-in must be today or later")


class Listing(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)
    listing_id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=300)
    city: str = Field(min_length=1, max_length=100)
    check_in: date
    check_out: date
    price: Decimal = Field(ge=0, max_digits=12, decimal_places=2, allow_inf_nan=False)
    currency: Literal["USD"]
    price_basis: Literal["per_night_taxes_included"]
    rating: Decimal = Field(ge=0, le=5, allow_inf_nan=False)
    rating_scale: Literal[5]
    source_url: HttpUrl
    extracted_at: AwareDatetime

    @model_validator(mode="after")
    def ordered_dates(self) -> Self:
        if not 1 <= (self.check_out - self.check_in).days <= 30:
            raise ValueError("Listing stay must contain 1 to 30 nights")
        return self


class Snapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    stay: Stay
    extracted_at: AwareDatetime
    listings: tuple[Listing, ...]

    @model_validator(mode="after")
    def consistent_records(self) -> Self:
        ids = [listing.listing_id for listing in self.listings]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate listing identifiers in one run")
        for listing in self.listings:
            if (listing.check_in, listing.check_out) != (self.stay.check_in, self.stay.check_out):
                raise ValueError("Listing dates do not match the requested stay")
            if self.stay.city and listing.city.casefold() != self.stay.city.casefold():
                raise ValueError("Listing city does not match the requested city")
            if listing.extracted_at != self.extracted_at:
                raise ValueError("Listing timestamps do not match the snapshot")
        return self
