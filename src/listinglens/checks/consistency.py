"""Claim consistency checks. These produce FACT flags: contradictions inside the listing's own data.

Every rule is a pure function `(Listing) -> list[Flag]`. Rules stay silent unless
BOTH sides of a contradiction are present, so missing data never produces a flag.
Phrase lists are deliberately conservative: a missed flag is better than a false one.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from listinglens.models import Evidence, Flag, Listing
from listinglens.text import capacities_gb, excerpt

# A phrase doesn't count if one of these words appears just before it ("like new", "not sealed").
NEGATION_WORDS = {"not", "never", "no", "like", "isn't", "wasn't", "non"}

NEW_PHRASES = [
    "brand new",
    "brand-new",
    "factory sealed",
    "sealed",
    "new in box",
    "nib",
    "bnib",
    "unopened",
    "never opened",
]
USED_PHRASES = [
    "pre-owned",
    "preowned",
    "previously owned",
    "second hand",
    "second-hand",
    "secondhand",
    "lightly used",
    "gently used",
    "barely used",
    "used condition",
    "refurbished",
]
NOT_WORKING_PHRASES = [
    "for parts",
    "parts only",
    "not working",
    "does not power on",
    "doesn't power on",
    "does not turn on",
    "doesn't turn on",
    "won't turn on",
    "dead on arrival",
]

# Capacities within this fraction count as equal ("1TB" vs "1000 GB").
CAPACITY_TOLERANCE = 0.05


def find_claim(text: str, phrases: list[str]) -> str | None:
    """First phrase found in text as whole words and not negated. Case-insensitive."""
    lowered = text.lower()
    for phrase in phrases:
        for match in re.finditer(rf"(?<![\w-]){re.escape(phrase)}(?![\w-])", lowered):
            preceding = lowered[: match.start()].split()[-2:]
            if not NEGATION_WORDS.intersection(preceding):
                return phrase
    return None


def _text_fields(listing: Listing) -> list[tuple[str, str]]:
    """(our field name, text) for the free-text fields claims can appear in."""
    fields = [
        ("title", listing.title),
        ("description_text", listing.description_text),
        ("condition_note", listing.condition_note or ""),
    ]
    return [(name, text) for name, text in fields if text]


def _condition_evidence(listing: Listing) -> Evidence:
    return Evidence(listing.source_path("condition"), excerpt(listing.condition_label))


def check_new_claim_vs_used_condition(listing: Listing) -> list[Flag]:
    if listing.condition not in {"USED", "FOR_PARTS"}:
        return []
    for name, text in _text_fields(listing):
        claim = find_claim(text, NEW_PHRASES)
        # A bare leading "New ..." in the title is also a claim of new.
        if claim is None and name == "title" and re.match(r"new\b", text, re.IGNORECASE):
            claim = "new"
        if claim:
            return [
                Flag(
                    rule_id="condition.new_claim_vs_used_condition",
                    message=f'The {name.replace("_", " ")} says "{claim}", '
                    f'but the condition field is "{listing.condition_label}".',
                    severity="high",
                    evidence=[
                        Evidence(listing.source_path(name), excerpt(text)),
                        _condition_evidence(listing),
                    ],
                )
            ]
    return []


def check_used_claim_vs_new_condition(listing: Listing) -> list[Flag]:
    if listing.condition != "NEW":
        return []
    for name, text in _text_fields(listing):
        claim = find_claim(text, USED_PHRASES)
        if claim:
            return [
                Flag(
                    rule_id="condition.used_claim_vs_new_condition",
                    message=f'The {name.replace("_", " ")} says "{claim}", '
                    f'but the condition field is "{listing.condition_label}".',
                    severity="high",
                    evidence=[
                        Evidence(listing.source_path(name), excerpt(text)),
                        _condition_evidence(listing),
                    ],
                )
            ]
    return []


def check_not_working_vs_condition(listing: Listing) -> list[Flag]:
    if listing.condition in {None, "FOR_PARTS"}:
        return []
    for name, text in _text_fields(listing):
        claim = find_claim(text, NOT_WORKING_PHRASES)
        if claim:
            return [
                Flag(
                    rule_id="condition.not_working_vs_condition",
                    message=f'The {name.replace("_", " ")} says "{claim}", but the condition field '
                    f'is "{listing.condition_label}" rather than "For parts or not working".',
                    severity="high",
                    evidence=[
                        Evidence(listing.source_path(name), excerpt(text)),
                        _condition_evidence(listing),
                    ],
                )
            ]
    return []


def check_capacity_title_vs_specifics(listing: Listing) -> list[Flag]:
    in_title = capacities_gb(listing.title)
    if not in_title:
        return []
    flags = []
    for aspect_name, values in listing.specifics.aspects.items():
        if "capacity" not in aspect_name.lower():
            continue
        for gb in capacities_gb(" ".join(values)):
            if not any(abs(gb - t) <= CAPACITY_TOLERANCE * gb for t in in_title):
                flags.append(
                    Flag(
                        rule_id="specs.capacity_title_vs_specifics",
                        message=f'Item specific "{aspect_name}" is {values[0]}, '
                        "but that capacity doesn't appear in the title.",
                        severity="high",
                        evidence=[
                            Evidence(listing.source_path("title"), excerpt(listing.title)),
                            Evidence(
                                listing.source_path(f"aspects.{aspect_name}"), excerpt(values[0])
                            ),
                        ],
                    )
                )
    return flags


_TITLE_QUANTITY_RE = re.compile(
    r"\b(?:lot of|pack of|set of)\s+(\d+)\b|\b(\d+)\s*(?:-?\s*pack|pcs|pieces)\b", re.IGNORECASE
)
QUANTITY_ASPECTS = ["Number in Pack", "Unit Quantity"]


def check_quantity_title_vs_specifics(listing: Listing) -> list[Flag]:
    match = _TITLE_QUANTITY_RE.search(listing.title)
    if not match:
        return []
    title_qty = int(match.group(1) or match.group(2))
    for aspect_name in QUANTITY_ASPECTS:
        value = listing.specifics.get(aspect_name)
        if value and value.strip().isdigit() and int(value) != title_qty:
            return [
                Flag(
                    rule_id="quantity.title_vs_specifics",
                    message=f'The title says "{match.group(0)}", '
                    f'but item specific "{aspect_name}" is {value}.',
                    # "warn": a lot of 3 single-pack items is arguably consistent. Worth a look.
                    severity="warn",
                    evidence=[
                        Evidence(listing.source_path("title"), excerpt(listing.title)),
                        Evidence(listing.source_path(f"aspects.{aspect_name}"), excerpt(value)),
                    ],
                )
            ]
    return []


def check_brand_field_vs_specifics(listing: Listing) -> list[Flag]:
    brand_field, brand_aspect = listing.specifics.brand, listing.specifics.get("Brand")
    if not brand_field or not brand_aspect:
        return []
    if brand_field.strip().lower() == brand_aspect.strip().lower():
        return []
    return [
        Flag(
            rule_id="brand.field_vs_specifics",
            message=f'The brand field is "{brand_field}", '
            f'but item specific "Brand" is "{brand_aspect}".',
            severity="high",
            evidence=[
                Evidence(listing.source_path("brand"), excerpt(brand_field)),
                Evidence(listing.source_path("aspects.Brand"), excerpt(brand_aspect)),
            ],
        )
    ]


RULES: list[Callable[[Listing], list[Flag]]] = [
    check_new_claim_vs_used_condition,
    check_used_claim_vs_new_condition,
    check_not_working_vs_condition,
    check_capacity_title_vs_specifics,
    check_quantity_title_vs_specifics,
    check_brand_field_vs_specifics,
]


def check_consistency(listing: Listing) -> list[Flag]:
    """Run every consistency rule and collect the flags."""
    return [flag for rule in RULES for flag in rule(listing)]
