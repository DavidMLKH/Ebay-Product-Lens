"""Command-line entry point: `listinglens analyze <item> --offline`."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from listinglens.checks.consistency import check_consistency
from listinglens.ebay.parse import parse_item
from listinglens.report import render_markdown
from listinglens.sources import FixtureSource

DEFAULT_FIXTURES = Path("tests/fixtures/ebay/items")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="listinglens", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    analyze = commands.add_parser("analyze", help="Analyze one listing and print a report.")
    analyze.add_argument("item", help="Item ID, or fixture name with --offline.")
    analyze.add_argument("--offline", action="store_true", help="Read from fixture files.")
    analyze.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURES, help="Fixture folder.")
    args = parser.parse_args(argv)

    if not args.offline:
        print("Live eBay API isn't available yet (Phase 4). Use --offline.", file=sys.stderr)
        return 2

    try:
        raw = FixtureSource(args.fixtures).get_item(args.item)
    except FileNotFoundError as error:
        print(error, file=sys.stderr)
        return 1

    listing = parse_item(raw)
    report = render_markdown(listing, check_consistency(listing), "fixture", datetime.now())
    # Windows consoles may not use UTF-8; never crash on an unusual character in listing text.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
