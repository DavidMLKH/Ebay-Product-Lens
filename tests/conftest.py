"""Shared test helpers. pytest loads this file automatically."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from listinglens.ebay.parse import parse_item
from listinglens.models import Listing
from listinglens.sources import FixtureSource

ITEMS_DIR = Path(__file__).parent / "fixtures" / "ebay" / "items"
FIXTURE_NAMES = sorted(p.stem for p in ITEMS_DIR.glob("*.json"))


def load_raw(name: str) -> dict[str, Any]:
    """Raw fixture JSON. Returns a deep copy so tests can modify it safely."""
    return copy.deepcopy(FixtureSource(ITEMS_DIR).get_item(name))


def load_listing(name: str) -> Listing:
    return parse_item(load_raw(name))
