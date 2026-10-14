import pytest
from conftest import FIXTURE_NAMES, load_listing, load_raw

from listinglens.checks.consistency import NEW_PHRASES, check_consistency, find_claim
from listinglens.ebay.parse import parse_item

# Fixture -> exactly the rule IDs it should trigger. Every fixture must be listed.
EXPECTED = {
    "clean_iphone": [],
    "new_title_used_condition": ["condition.new_claim_vs_used_condition"],
    "used_text_new_condition": ["condition.used_claim_vs_new_condition"],
    "capacity_mismatch": ["specs.capacity_title_vs_specifics"],
    "quantity_mismatch": ["quantity.title_vs_specifics"],
    "for_parts_text_used_condition": ["condition.not_working_vs_condition"],
    "missing_fields": [],
    "like_new_negation": [],
    "restrictive_returns": [],
    "low_feedback_high_value": [],
}


def test_every_fixture_has_an_expectation():
    assert sorted(EXPECTED) == FIXTURE_NAMES


@pytest.mark.parametrize("name, expected_rules", EXPECTED.items())
def test_fixture_flags(name, expected_rules):
    flags = check_consistency(load_listing(name))
    assert [f.rule_id for f in flags] == expected_rules


def test_flags_are_facts_with_evidence():
    for name in FIXTURE_NAMES:
        for flag in check_consistency(load_listing(name)):
            assert flag.kind == "fact"
            assert len(flag.evidence) >= 2  # both sides of the contradiction


def test_capacity_flag_cites_exact_source_fields():
    [flag] = check_consistency(load_listing("capacity_mismatch"))
    paths = [e.field_path for e in flag.evidence]
    assert paths == ["title", "localizedAspects[Storage Capacity]"]
    assert flag.evidence[1].value_excerpt == "128 GB"


def test_condition_flag_cites_title_and_condition():
    [flag] = check_consistency(load_listing("new_title_used_condition"))
    assert [e.field_path for e in flag.evidence] == ["title", "condition"]


def test_brand_mismatch_between_field_and_specifics():
    raw = load_raw("clean_iphone")
    raw["brand"] = "Samsung"  # item specifics still say Apple
    [flag] = check_consistency(parse_item(raw))
    assert flag.rule_id == "brand.field_vs_specifics"
    assert [e.field_path for e in flag.evidence] == ["brand", "localizedAspects[Brand]"]


def test_tb_and_gb_within_tolerance_do_not_flag():
    raw = load_raw("low_feedback_high_value")
    raw["localizedAspects"][2]["value"] = "1000 GB"  # title says 1TB
    assert check_consistency(parse_item(raw)) == []


# --- Missing data must never produce a flag ---


def test_no_condition_means_no_condition_flags():
    raw = load_raw("new_title_used_condition")
    del raw["conditionId"]
    assert check_consistency(parse_item(raw)) == []


def test_no_capacity_in_title_means_no_capacity_flag():
    raw = load_raw("capacity_mismatch")
    raw["title"] = "Apple iPhone 13 Midnight Unlocked"
    assert check_consistency(parse_item(raw)) == []


# --- Negation and phrase matching ---


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Brand new in box", "brand new"),
        ("Factory sealed iPhone", "factory sealed"),
        ("Like new condition", None),
        ("Not new in box, opened once", None),
        ("It is not sealed", None),
        ("Newest model", None),  # whole words only
        ("Resealed by seller", None),
    ],
)
def test_find_new_claim(text, expected):
    assert find_claim(text, NEW_PHRASES) == expected
