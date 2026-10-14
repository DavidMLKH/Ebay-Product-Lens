"""Pure text helpers: HTML to text, excerpts, and extracting simple claims from text."""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

EXCERPT_MAX_CHARS = 120


def html_to_text(html: str | None) -> str:
    """Strip HTML to plain text. Script/style contents are dropped, not kept as text."""
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    return collapse_whitespace(soup.get_text(separator=" "))


def collapse_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def excerpt(text: str | None, max_chars: int = EXCERPT_MAX_CHARS) -> str:
    """Short single-line quote of untrusted text, for evidence."""
    text = collapse_whitespace(text or "")
    return text if len(text) <= max_chars else text[: max_chars - 1] + "…"


# "128GB", "128 GB", "1TB", "1.5 TB". The lookarounds stop "1128GB" matching as "128GB".
_CAPACITY_RE = re.compile(r"(?<![\d.])(\d+(?:\.\d+)?)\s*(TB|GB)\b", re.IGNORECASE)


def capacities_gb(text: str | None) -> set[int]:
    """All storage capacities mentioned in the text, normalized to whole GB."""
    found = set()
    for number, unit in _CAPACITY_RE.findall(text or ""):
        gb = float(number) * (1024 if unit.upper() == "TB" else 1)
        found.add(round(gb))
    return found
