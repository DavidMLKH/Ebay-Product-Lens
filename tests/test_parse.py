from decimal import Decimal

import pytest
from conftest import FIXTURE_NAMES, load_listing


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_every_fixture_parses(name):
    listing = load_listing(name)
    assert listing.source == "ebay"
    assert listing.title


def test_clean_listing_fields():
    listing = load_listing("clean_iphone")
    assert listing.price.value == Decimal("389.00")
    assert listing.condition == "USED"
    assert listing.condition_label == "Used"
    assert listing.returns.accepted is True
    assert listing.returns.period_days == 30
    assert listing.seller.feedback_score == 4210
    assert listing.seller.feedback_percent == 99.6
    assert listing.shipping.free is True
    assert listing.specifics.get("storage capacity") == "128 GB"  # case-insensitive lookup
    assert listing.specifics.gtin == "194252707326"
    assert len(listing.image_urls) == 2


def test_field_paths_point_at_source_fields():
    listing = load_listing("clean_iphone")
    assert listing.source_path("aspects.Storage Capacity") == "localizedAspects[Storage Capacity]"
    assert listing.source_path("condition_note") == "conditionDescription"


def test_missing_fields_become_none_not_defaults():
    listing = load_listing("missing_fields")
    assert listing.condition is None
    assert listing.description_text == ""
    assert listing.returns.accepted is None  # "didn't say", not "no returns"
    assert listing.seller.feedback_score is None
    assert listing.shipping.cost is None
    assert listing.shipping.free is None
    assert listing.specifics.aspects == {}


def test_html_is_stripped_and_scripts_dropped():
    listing = load_listing("restrictive_returns")
    assert "<" not in listing.description_text
    assert "alert" not in listing.description_text
