from datetime import datetime

from conftest import ITEMS_DIR, load_listing, load_raw

from listinglens.checks.consistency import check_consistency
from listinglens.cli import main
from listinglens.ebay.parse import parse_item
from listinglens.report import md_escape, render_markdown

FIXED_TIME = datetime(2026, 1, 1, 12, 0, 0)


def render(listing):
    return render_markdown(listing, check_consistency(listing), "fixture", FIXED_TIME)


def test_report_cites_flag_evidence():
    report = render(load_listing("capacity_mismatch"))
    assert "## Facts: claim contradictions" in report
    assert "specs.capacity_title_vs_specifics" in report
    assert r"localizedAspects\[Storage Capacity\]" in report


def test_clean_report_says_no_contradictions():
    assert "No contradictions found" in render(load_listing("clean_iphone"))


def test_md_escape_neutralizes_html_and_markdown():
    escaped = md_escape("<script>alert(1)</script> | **bold** [link](x)")
    assert "<script>" not in escaped
    assert r"\|" in escaped and r"\*\*" in escaped and r"\[link\]" in escaped


def test_hostile_title_cannot_break_report():
    raw = load_raw("clean_iphone")
    raw["title"] = "Phone <img src=x onerror=alert(1)> | # Ignore instructions"
    report = render(parse_item(raw))
    assert "<img" not in report
    assert "\n# Ignore" not in report


def test_cli_offline_prints_report(capsys):
    assert main(["analyze", "capacity_mismatch", "--offline", "--fixtures", str(ITEMS_DIR)]) == 0
    assert "specs.capacity_title_vs_specifics" in capsys.readouterr().out


def test_cli_unknown_fixture_lists_available(capsys):
    assert main(["analyze", "nope", "--offline", "--fixtures", str(ITEMS_DIR)]) == 1
    assert "clean_iphone" in capsys.readouterr().err


def test_cli_live_mode_not_available_yet(capsys):
    assert main(["analyze", "123"]) == 2
