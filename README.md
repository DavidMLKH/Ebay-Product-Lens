# ListingLens (Ebay-Product-Lens)

Flags inconsistent claims and suspicious signals in eBay listings. Later phases will also find equivalent products from more trustworthy sellers.

**Status:** Phase 1. Claim-consistency checks run offline on synthetic fixtures. Live eBay API support comes in Phase 4. See [docs/DESIGN.md](docs/DESIGN.md).

## Quick start (Windows PowerShell)

```powershell
python -m venv .venv; .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
listinglens analyze capacity_mismatch --offline
pytest
```

Reports separate **facts** (contradictions in the listing's own data, with the exact fields cited) from **heuristics** (judgment calls, Phase 2). They are signals, not verdicts.
