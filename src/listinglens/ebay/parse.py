"""Convert a raw eBay Browse API `getItem` response (a dict) into a Listing.

This is the only module that knows eBay's JSON layout. It is pure: no network,
no disk. Anything missing in the input becomes None. We never guess a value.

Field names follow eBay's documented Browse API schema. Verify them against a
live response in Phase 4 (see docs/DESIGN.md).
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from listinglens.models import ItemSpecifics, Listing, Money, ReturnPolicy, Seller, Shipping
from listinglens.text import html_to_text

# eBay conditionId -> our condition group. IDs are stable; display text is not.
CONDITION_GROUPS = {
    "1000": "NEW",
    "1500": "NEW_OTHER",  # new, open box / no original packaging
    "1750": "NEW_OTHER",  # new with defects
    "2000": "REFURBISHED",
    "2010": "REFURBISHED",
    "2020": "REFURBISHED",
    "2030": "REFURBISHED",
    "2500": "REFURBISHED",
    "2750": "USED",  # "Like New" is still a used item
    "3000": "USED",
    "4000": "USED",
    "5000": "USED",
    "6000": "USED",
    "7000": "FOR_PARTS",
}


def parse_item(raw: dict[str, Any]) -> Listing:
    aspects: dict[str, list[str]] = {}
    for aspect in raw.get("localizedAspects") or []:
        name, value = aspect.get("name"), aspect.get("value")
        if name and value:
            aspects.setdefault(name, []).append(str(value))

    field_paths = {
        "title": "title",
        "description_text": "description",
        "condition": "condition",
        "condition_note": "conditionDescription",
        "price": "price.value",
        "brand": "brand",
    }
    for name in aspects:
        field_paths[f"aspects.{name}"] = f"localizedAspects[{name}]"

    images = [
        img.get("imageUrl")
        for img in [raw.get("image") or {}] + (raw.get("additionalImages") or [])
    ]

    return Listing(
        source="ebay",
        item_id=str(raw.get("itemId", "")),
        url=raw.get("itemWebUrl"),
        title=raw.get("title") or "",
        description_text=html_to_text(raw.get("description")),
        condition=CONDITION_GROUPS.get(str(raw.get("conditionId", ""))),
        condition_label=raw.get("condition"),
        condition_note=raw.get("conditionDescription"),
        price=_money(raw.get("price")),
        shipping=_shipping(raw),
        returns=_returns(raw.get("returnTerms")),
        seller=_seller(raw.get("seller") or {}),
        specifics=ItemSpecifics(
            aspects=aspects,
            brand=raw.get("brand"),
            mpn=raw.get("mpn"),
            gtin=raw.get("gtin"),
            epid=raw.get("epid"),
        ),
        image_urls=[url for url in images if url],
        field_paths=field_paths,
        raw=raw,
    )


def _money(data: dict[str, Any] | None) -> Money | None:
    if not data or data.get("value") is None:
        return None
    try:
        return Money(Decimal(str(data["value"])), data.get("currency", "USD"))
    except InvalidOperation:
        return None


def _shipping(raw: dict[str, Any]) -> Shipping:
    costs = [_money(opt.get("shippingCost")) for opt in raw.get("shippingOptions") or []]
    costs = [c for c in costs if c is not None]
    return Shipping(
        cost=min(costs, key=lambda m: m.value) if costs else None,
        ships_from_country=(raw.get("itemLocation") or {}).get("country"),
    )


def _returns(data: dict[str, Any] | None) -> ReturnPolicy:
    if not data:
        return ReturnPolicy(accepted=None, period_days=None, payer=None)
    period = data.get("returnPeriod") or {}
    return ReturnPolicy(
        accepted=data.get("returnsAccepted"),
        period_days=period.get("value"),
        payer=data.get("returnShippingCostPayer"),
    )


def _seller(data: dict[str, Any]) -> Seller:
    percent = data.get("feedbackPercentage")
    return Seller(
        username=data.get("username") or "",
        feedback_score=data.get("feedbackScore"),
        feedback_percent=float(percent) if percent is not None else None,
        account_type=data.get("sellerAccountType"),
    )
