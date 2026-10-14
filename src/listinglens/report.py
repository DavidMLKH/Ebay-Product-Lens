"""Render analysis results as a Markdown report. Pure: data in, string out.

All listing text is untrusted. It goes through `md_escape` so it can't break the
report's formatting or inject HTML.
"""

from __future__ import annotations

import re
from datetime import datetime

from listinglens.models import Flag, Listing

DISCLAIMER = (
    "_These are signals, not verdicts. A flag means something in the listing deserves a "
    "closer look; it does not mean the seller is dishonest._"
)


def md_escape(text: str) -> str:
    """Make untrusted text display literally in Markdown (and in any HTML it's rendered to)."""
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = re.sub(r"([\\`*_{}\[\]()#+!|~])", r"\\\1", text)
    return text.replace("\n", " ")


def render_markdown(
    listing: Listing, flags: list[Flag], data_source: str, generated_at: datetime
) -> str:
    price = f"{listing.price.value} {listing.price.currency}" if listing.price else "not provided"
    lines = [
        f"# ListingLens report: {md_escape(listing.title)}",
        "",
        f"- **Item:** {md_escape(listing.item_id)} ({listing.source})",
        f"- **Price:** {price}",
        f"- **Condition:** {md_escape(listing.condition_label or 'not provided')}",
        f"- **Seller:** {md_escape(listing.seller.username or 'not provided')}",
        f"- **Data source:** {data_source}",
        f"- **Generated:** {generated_at.isoformat(timespec='seconds')}",
        "",
        "## Facts: claim contradictions",
        "",
    ]
    if not flags:
        lines.append("No contradictions found in the fields checked.")
    for flag in flags:
        lines += [
            f"### [{flag.severity.upper()}] {md_escape(flag.message)}",
            "",
            f"Rule: `{flag.rule_id}`",
            "",
            "| Field | Value |",
            "|---|---|",
        ]
        # Field paths can contain seller-written aspect names, so they're escaped too.
        lines += [
            f"| {md_escape(e.field_path)} | {md_escape(e.value_excerpt)} |" for e in flag.evidence
        ]
        lines.append("")
    lines += [
        "",
        "## Heuristic signals",
        "",
        "_Not implemented yet (Phase 2)._",
        "",
        "---",
        DISCLAIMER,
        "",
    ]
    return "\n".join(lines)
