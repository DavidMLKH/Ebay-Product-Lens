"""Where raw listing data comes from: saved fixture files now, the live eBay API later.

`Source` is a Protocol: any object with a matching `get_item` method counts as a
Source, no inheritance needed. Two implementations exist (fixtures now, live
client in Phase 4), so this abstraction isn't speculative.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol


class Source(Protocol):
    def get_item(self, item_id: str) -> dict[str, Any]:
        """Raw item JSON for one listing."""
        ...


class FixtureSource:
    """Reads `<item_id>.json` from a folder. No network. Used for tests and offline runs."""

    def __init__(self, folder: Path) -> None:
        self.folder = Path(folder)

    def get_item(self, item_id: str) -> dict[str, Any]:
        path = self.folder / f"{item_id}.json"
        if not path.exists():
            available = ", ".join(sorted(p.stem for p in self.folder.glob("*.json")))
            raise FileNotFoundError(f"No fixture '{item_id}'. Available: {available}")
        return json.loads(path.read_text(encoding="utf-8"))
