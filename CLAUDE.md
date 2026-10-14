# ListingLens

ListingLens (working name) is a Python tool that analyzes online marketplace listings. It flags inconsistent claims and suspicious signals, then finds equivalent products from more trustworthy sellers. **eBay is the only marketplace for now** because it has an official API. Others may come later.

The full approved design (data model, algorithms, roadmap, risks) is in [docs/DESIGN.md](docs/DESIGN.md). Read it before starting a new phase.

## Decisions made (2026-10-13)

- **eBay-only, using official APIs.** No web scraping: it's against most sites' terms, breaks easily, and lacks seller trust data. Any future source must be an official API that outputs `Listing`.
- **Marketplace:** `EBAY_US`, USD, English text rules.
- **Focus category:** consumer electronics (phones, laptops, headphones). Fixtures and rules target this first.
- **Audience:** the owner only, run locally. Reports are never published.

## Current status

- **eBay API keys: not yet available** (Developer Program signup is pending). Everything runs on synthetic fixtures until Phase 4.
- Phase 1 (offline skeleton + claim consistency checks): **in progress**
- Phases 2–5: not started (see docs/DESIGN.md §5)

## Who you're working with

The owner is an intermediate Python developer, and this is their first real project.
- **Explain decisions briefly as you make them**, in one or two sentences: why this library, why this structure, what the tradeoff is. Teach without lecturing.
- Prefer plain, readable Python over clever Python. If you use an idiom they may not know (e.g. `functools.cache`, `Protocol`, dataclass `field(default_factory=...)`), add a one-line note when you introduce it.
- When a decision is genuinely theirs (scope, product behavior, paid services), ask. Don't pick silently.

## What the tool does (target scope)

1. **Fetch** a listing: title, description, price, shipping, return policy, seller stats, item specifics, images.
2. **Check inconsistencies**: e.g. title says "brand new" but the condition or description says "used", item specifics that contradict each other or the title, a price far below comparable listings.
3. **Flag suspicious signals**: e.g. a new or low-feedback seller with many high-value listings, vague or copied descriptions, an unusually restrictive shipping or return policy.
4. **Find equivalents**: search for the same product and rank results by seller trustworthiness and price.
5. **Report**: every flag cites the exact fields behind it, and facts are kept separate from heuristic judgments.

Build these in order, one working slice at a time. Don't scaffold later stages before earlier ones work end to end.

## Core design rules (non-negotiable)

These rules are what make the tool trustworthy, so they matter more than any feature.

- **Every flag cites evidence.** A flag holds the field paths and the values it relied on (e.g. `title = "Brand New iPhone 15"`, `condition = "Used"`). A flag with no evidence is a bug.
- **Facts vs. heuristics are different types.** A *fact* is a direct, checkable observation from the data ("condition field is `USED`, title contains `new`"). A *heuristic* is a judgment with a threshold ("price is 62% below the median of 14 comparables"). Every flag carries a `kind` of `"fact"` or `"heuristic"`. Heuristics also state their threshold and the inputs used (e.g. sample size). Reports show the two in separate sections.
- **Never invent data.** If the API doesn't return a field (e.g. seller account age), record it as *unavailable* and say so in the report. Don't guess or fill in defaults that look like real values. Missing data is information too.
- **Neutral wording.** Flags describe signals ("price is far below comparables"). They don't accuse ("this is a scam"). The tool informs a buyer's judgment; it doesn't replace it.
- **Rules are small, pure, and testable.** Each check is a plain function: normalized listing (plus context such as comparables) in, list of flags out. No network calls inside rules.

## Architecture

```
src/listinglens/
  models.py        # dataclasses: Listing, Seller, Flag, Evidence, Report
  ebay/            # everything eBay-specific: auth, API client, raw JSON -> Listing
  checks/          # rule functions: inconsistencies.py, signals.py, pricing.py
  search.py        # find + rank equivalent listings
  report.py        # render Report (text/markdown first; JSON if needed)
  cli.py           # entry point
tests/
  fixtures/        # saved eBay API responses (JSON) used by tests
```

- **The boundary for future marketplaces is the normalized `Listing` model.** eBay code converts eBay JSON into `Listing`. Checks, search ranking, and reports only ever see `Listing`. That alone keeps the design open to new marketplaces. **Don't** build a plugin registry, abstract base classes, or marketplace config until a second marketplace actually exists.
- Keep the raw API response next to the normalized listing (or keep a field map) so evidence can point back to the original eBay field.
- Use standard-library `dataclasses` for models. Add pydantic only if validation becomes a real pain, and explain why when you do.

## eBay API notes

- Primary API: **Browse API** (`getItem`, `item_summary/search`), using OAuth **client-credentials** (application token). Use the **Sandbox** environment during development and switch with a single setting.
- Check what the Browse API actually returns before designing a rule around it. Some seller details (e.g. account age, total active listings) may not be available. Mark these unavailable rather than working around them silently, and raise it with the owner.
- Respect rate limits and eBay's API License Agreement, especially around caching and storing listing data. Cache responses during development to avoid hammering the API.
- **Secrets**: credentials live in a `.env` file loaded from environment variables. `.env` must be in `.gitignore`. Never print, log, or commit tokens or keys. Provide a `.env.example` with placeholder names only.

## Tech & conventions

- Python **3.13** (installed locally); code should also run on 3.11+.
- Use a virtual environment in `.venv`, with dependencies declared in `pyproject.toml`. Keep dependencies few. Add one only when it clearly earns its place, and say why.
- Suggested baseline: `httpx` (HTTP), `python-dotenv` (config), `pytest` (tests), `ruff` (lint + format). Confirm with the owner before adding anything heavier (pydantic, LLM SDKs, databases, web frameworks).
- Type hints on public functions. Follow `ruff` defaults with a line length of 100.
- The dev machine is **Windows** (PowerShell). Give commands that work there, e.g. `.venv\Scripts\Activate.ps1`.

```powershell
python -m venv .venv; .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest
ruff check . ; ruff format .
```

## Testing

- **Tests never hit the live API.** Use saved JSON responses in `tests/fixtures/`, and scrub them of anything sensitive.
- Every check gets tests for: a listing that should flag it, a clean listing that shouldn't, and a listing with the relevant field missing.
- When you fix a bug, first write a test that reproduces it.
- Heuristic thresholds live as named constants beside the rule, and tests cover the boundary.

## Working guidelines (Karpathy guidelines)

These guidelines reduce common LLM coding mistakes. They favor caution over speed; for trivial tasks, use judgment.

### 1. Think before coding
**Don't assume. Don't hide confusion. Surface tradeoffs.**
- State assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them. Don't pick silently.
- If a simpler approach exists, say so, and push back when warranted.
- If something is unclear, stop, name what's confusing, and ask.

### 2. Simplicity first
**Minimum code that solves the problem. Nothing speculative.**
- No features beyond what was asked, and no abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested. In this project that especially means no multi-marketplace framework yet (see Architecture).
- No error handling for impossible scenarios. Handle the real ones: API errors, rate limits, missing fields.
- If you write 200 lines and it could be 50, rewrite it. Ask: "Would a senior engineer call this overcomplicated?"

### 3. Surgical changes
**Touch only what you must. Clean up only your own mess.**
- Don't "improve" adjacent code, comments, or formatting, and don't refactor what isn't broken.
- Match the existing style.
- Mention unrelated dead code; don't delete it.
- Remove imports, variables, and functions that *your* change made unused, and nothing else.
- Test: every changed line traces directly to the request.

### 4. Goal-driven execution
**Define success criteria. Loop until verified.**
- "Add a check" → write tests for flagged, clean, and missing-field listings, then make them pass.
- "Fix the bug" → write a test that reproduces it, then make it pass.
- "Refactor X" → tests pass before and after.
- For multi-step tasks, state a brief plan first:
  ```
  1. [Step] → verify: [check]
  2. [Step] → verify: [check]
  ```

## Git

- Small commits, one logical change each, with an imperative subject line ("Add title/condition mismatch check").
- Never commit `.env`, tokens, `.venv/`, or cached API responses containing real seller data.
- `claude-usage/` is an unrelated cloned repo. Don't modify it and don't commit it as part of this project.
