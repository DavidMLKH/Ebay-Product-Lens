"""Core data model. Every marketplace converts its raw data into these classes.

Checks, scoring and reports only ever see these classes. That is what keeps the
rest of the code independent of eBay's JSON layout.

Naming convention for comments below:
    fact    = copied from the source as-is
    derived = computed by us
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Literal


@dataclass(frozen=True)
class Money:
    value: Decimal  # fact. Decimal (not float) so money arithmetic is exact.
    currency: str  # fact, e.g. "USD"


@dataclass(frozen=True)
class Shipping:
    cost: Money | None  # fact: cheapest shipping option; None = not provided
    ships_from_country: str | None  # fact, e.g. "US"

    @property
    def free(self) -> bool | None:  # derived
        return None if self.cost is None else self.cost.value == 0


@dataclass(frozen=True)
class ReturnPolicy:
    accepted: bool | None  # fact; None = the listing didn't say
    period_days: int | None  # fact
    payer: str | None  # fact: "BUYER" or "SELLER"


@dataclass(frozen=True)
class Seller:
    username: str  # fact
    feedback_score: int | None  # fact
    feedback_percent: float | None  # fact, e.g. 99.2
    account_type: str | None  # fact: "BUSINESS" / "INDIVIDUAL"


@dataclass(frozen=True)
class ItemSpecifics:
    # fact: eBay "item specifics" / localizedAspects, e.g. {"Brand": ["Apple"]}
    aspects: dict[str, list[str]] = field(default_factory=dict)
    brand: str | None = None  # fact
    mpn: str | None = None  # fact: manufacturer part number
    gtin: str | None = None  # fact: UPC / EAN barcode
    epid: str | None = None  # fact: eBay product ID

    def get(self, name: str) -> str | None:
        """First value of an aspect, matched case-insensitively. None if absent."""
        for key, values in self.aspects.items():
            if key.lower() == name.lower() and values:
                return values[0]
        return None


@dataclass(frozen=True)
class Listing:
    source: str  # fact: which marketplace, e.g. "ebay"
    item_id: str  # fact
    url: str | None  # fact
    title: str  # fact
    description_text: str  # derived: description with HTML stripped
    condition: str | None  # fact: normalized condition, e.g. "NEW", "USED", "FOR_PARTS"
    condition_label: str | None  # fact: marketplace's own wording, e.g. "Used"
    condition_note: str | None  # fact: seller's free-text condition description
    price: Money | None  # fact
    shipping: Shipping  # fact
    returns: ReturnPolicy  # fact
    seller: Seller  # fact
    specifics: ItemSpecifics  # fact
    image_urls: list[str] = field(default_factory=list)  # fact
    # Where each of our fields came from in the raw source data, used as evidence.
    # e.g. {"title": "title", "aspects.Storage Capacity": "localizedAspects[Storage Capacity]"}
    field_paths: dict[str, str] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict, repr=False)  # fact: original JSON

    def source_path(self, our_field: str) -> str:
        """Source field path for one of our fields, falling back to our own name."""
        return self.field_paths.get(our_field, our_field)


@dataclass(frozen=True)
class Evidence:
    field_path: str  # path in the source data, e.g. "localizedAspects[Brand]"
    value_excerpt: str  # the value we relied on, truncated (untrusted text: never interpreted)


Severity = Literal["info", "warn", "high"]


@dataclass(frozen=True)
class Flag:
    """A FACT-level finding: a direct, checkable contradiction in the listing's own data."""

    rule_id: str  # e.g. "condition.title_vs_condition"
    message: str  # neutral wording: describes what was seen, never accuses
    severity: Severity
    evidence: list[Evidence]
    kind: Literal["fact"] = "fact"
