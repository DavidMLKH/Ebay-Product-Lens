# ListingLens — Design Plan (v1)

## Context
The repo is empty apart from `README.md` and `CLAUDE.md`, which already holds the conventions: an eBay-first `Listing` model, facts kept separate from heuristics, every flag citing evidence, and the Karpathy guidelines. The owner just signed up for the eBay Developer Program and **has no API keys yet**. They asked for a full design (structure, data model, features, algorithms, roadmap, risks) and for a decision: *eBay-only, or scan the whole web?* No implementation code at this step.

---

## 0. Decision: eBay-only for v1 (not whole-web)

**Recommendation: eBay-only, through the official API. Keep the `Listing` model as the one place where other sources plug in later.**

Why not scan the whole web:
- **Legal/ToS:** most retailer sites forbid scraping, so the core feature would rely on breaking their terms.
- **Brittle:** every site has different HTML and anti-bot protection, so you'd spend most of your time maintaining scrapers instead of building analysis.
- **Data quality:** the trust signals depend on structured seller stats (feedback score and %, return terms, item specifics). eBay's API provides these, but arbitrary web pages mostly don't.
- **Scope:** "a few weeks, first project" fits one source done well. The whole web is a different product.

**Path to "more than eBay" later (not v1):** add one *official* API at a time (for example Best Buy's public Products API, the Etsy Open API, or a paid shopping-search API for price comparison only). Each one is a new module that outputs `Listing`, with no changes to checks, trust scoring, or reports.

**No API key yet is fine.** Phases 1–3 run entirely on hand-made fixtures shaped like Browse API responses. The live client is Phase 4.

---

## 1. Project structure

```
Ebay-Product-Lens/
  CLAUDE.md  README.md  pyproject.toml  .env.example  .gitignore
  src/listinglens/
    __init__.py
    config.py          # reads env vars (.env): keys, sandbox/prod, marketplace, cache dir     [no network]
    models.py          # dataclasses (section 2)                                               [pure]
    thresholds.py      # every tunable number, named + commented, in one place                 [pure]
    text.py            # HTML→text, normalization, tokenizing, shingles                        [pure]
    sources.py         # `Source` Protocol: get_item(id), search(query) + FixtureSource         [disk only]
    ebay/
      auth.py          # OAuth client-credentials token, cached until expiry                   [NETWORK]
      client.py        # EbaySource: getItem / search, retries, rate-limit, disk cache          [NETWORK]
      cache.py         # tiny JSON-on-disk cache keyed by request, with TTL                     [disk only]
      parse.py         # raw Browse JSON → Listing (+ field paths for evidence)                 [pure]
    checks/
      consistency.py   # claim contradictions → FACT flags                                      [pure]
      signals.py       # seller/listing heuristics → HEURISTIC signals                          [pure]
      pricing.py       # price vs comparables                                                   [pure]
    trust.py           # signals → TrustScore (score, band, confidence, reasons)                [pure]
    matching.py        # pairwise "same product?" scoring                                      [pure]
    pipeline.py        # the ONLY orchestrator: source → parse → checks → search → rank          [calls Source]
    report.py          # Report → Markdown + JSON                                              [pure]
    cli.py             # `listinglens analyze <item-id> [--offline]`
  tests/
    fixtures/ebay/items/*.json      # synthetic getItem responses, one per scenario
    fixtures/ebay/searches/*.json   # synthetic search results (comparables)
    test_parse.py  test_consistency.py  test_signals.py  test_pricing.py
    test_trust.py  test_matching.py  test_report.py  test_pipeline_offline.py
```

**Network rule:** only `ebay/auth.py` and `ebay/client.py` touch the network. Everything in `checks/`, `trust.py`, `matching.py`, `report.py`, `parse.py` and `text.py` is pure: data in, data out, no I/O. `pipeline.py` receives a `Source`, so tests pass it a `FixtureSource`.
*Why a Protocol here when CLAUDE.md says no premature abstraction:* two real implementations exist from day one (fixtures and live), so it isn't speculative.

**Dependencies**
| Package | Why |
|---|---|
| `httpx` | HTTP client with timeouts. Its built-in `MockTransport` lets us test the client without extra mocking libraries |
| `python-dotenv` | Loads API keys from `.env` so they never end up in code |
| `beautifulsoup4` | eBay descriptions are HTML, and checks need plain text |
| `rapidfuzz` | Fast, well-tested fuzzy string matching for titles (token-set ratio) |
| `pytest` (dev) | Tests |
| `ruff` (dev) | Lint and format in one tool |

The CLI uses stdlib `argparse` and reports use plain f-strings, so no typer or jinja are needed for v1.

---

## 2. Data model (`models.py`)
**F** = fact copied from the source. **D** = derived by us. Every F field keeps its source path (e.g. `returnTerms.returnPeriod.value`) so evidence can cite it.

**Listing:** `source` (F, "ebay"), `item_id` F, `url` F, `title` F, `description_text` D (HTML stripped), `description_html` F (stored, never rendered), `condition` F (eBay enum, e.g. NEW/USED), `condition_note` F, `category_path` F, `price: Money` F, `shipping: Shipping` F, `returns: ReturnPolicy` F, `seller: Seller` F, `specifics: ItemSpecifics` F, `image_urls` F, `quantity_available` F|None, `quantity_sold` F|None, `created_at` F|None, `item_location_country` F|None, `raw` F (original JSON), `total_cost` D (price + cheapest shipping).

**Seller:** `username` F, `feedback_score` F|None, `feedback_percent` F|None, `account_type` F|None (business or individual), `registration_date` F|None (**likely unavailable from the Browse API**, see Risks), `active_listing_count` D|None (from a seller-filtered search), `high_value_listing_count` D|None.

**ItemSpecifics:** `aspects: dict[str, list[str]]` F (eBay `localizedAspects`), plus normalized shortcuts `brand` F, `mpn` F, `gtin` F (UPC/EAN), `epid` F, `model` F|None, `size` F|None, `color` F|None. `gtin_valid` D (checksum).

**Money:** `value: Decimal` F, `currency` F. *Decimal, not float, avoids rounding errors in money.*
**Shipping:** `cost: Money|None` F, `free` D, `handling_days_max` F|None, `ships_to_buyer_country` F|None, `options` F (raw list).
**ReturnPolicy:** `accepted` F|None, `period_days` F|None, `payer` F|None (BUYER/SELLER), `refund_method` F|None.

**Evidence:** `field_path` (e.g. `title`, `localizedAspects[Brand]`), `value_excerpt` (≤120 chars, escaped), `listing_id`.
**Flag** (output of consistency checks): `rule_id`, `kind = "fact"`, `message`, `evidence: list[Evidence]`, `severity` (info/warn/high).
**Signal** (output of heuristic checks): `name`, `kind = "heuristic"`, `score: float|None` (0 = risky, 1 = reassuring, None = not assessable), `weight`, `threshold_note` (e.g. "price < 0.6 × median of 14 comparables"), `inputs` (e.g. n=14), `evidence`, `missing_fields: list[str]`.
**TrustScore:** `score_0_100: int|None`, `band` (Good / Mixed / Caution / Insufficient data), `confidence` (low/med/high), `coverage: float`, `reasons: list[str]` (top contributors), `caps_applied: list[str]`.
**Match:** `candidate: Listing`, `method` ("gtin" / "epid" / "brand+mpn" / "fuzzy"), `similarity: float`, `confidence`, `disagreements: list[str]`.
**Report:** `listing`, `flags`, `signals`, `trust`, `not_assessed: list[str]`, `equivalents: list[(Match, TrustScore)]`, `generated_at`, `data_source` ("fixture" or "live").

---

## 3. Feature plan

### 3.1 eBay ingestion (`ebay/`, `sources.py`)
- **Auth:** OAuth2 *client-credentials* grant to `/identity/v1/oauth2/token` with scope `https://api.ebay.com/oauth/api_scope`. The token lasts about 2 hours, so cache it in memory and refresh when it expires. Sandbox and production use different hosts and keys, chosen by `EBAY_ENV`.
- **Endpoints (Browse API):** `GET /buy/browse/v1/item/{item_id}` (full listing), `GET /buy/browse/v1/item/get_item_by_legacy_id` (for the numeric IDs in eBay URLs), and `GET /buy/browse/v1/item_summary/search` (with `q`, `gtin`, `epid`, `category_ids`, `filter=conditionIds:{..},price:[..],sellers:{username}`). Send the header `X-EBAY-C-MARKETPLACE-ID: EBAY_US` (assumed).
- **Pagination:** `limit`/`offset`. We only need the first 50–100 comparables, so cap at 2 pages. *Never paginate "everything".*
- **Rate limits:** the Browse API default is about **5,000 calls/day per app**. Budget per analysis is 1 getItem + 1–2 searches + 1 seller search + ≤5 getItem for top equivalents, so ≤10 calls. Handle 429 by backing off and retrying up to 3 times, then failing with a clear message.
- **Caching:** disk JSON cache keyed by URL+params, TTL a few hours, used during development to save quota. Respect the API License's limits on storing data (verify exact terms).
- **Errors:** 404 → "listing ended or not found". 401 → refresh the token once. 5xx or timeout → retry with backoff. Malformed JSON → `parse.py` records missing fields rather than crashing.
- **Tests:** `parse.py` against fixtures (pure). `client.py` with `httpx.MockTransport` (token refresh, 429 retry, 404). No live calls in the test suite.

### 3.2 Claim consistency checks (`checks/consistency.py`) → FACT flags
Input: `Listing`. Output: `list[Flag]`. Each rule is a small function that extracts claims from title, description and specifics and compares them.
- **Condition:** title or description says "new / brand new / sealed / NIB" while `condition` is a USED/REFURB enum, or the reverse ("used", "pre-owned", "for parts", "doesn't work") with condition NEW. Negation guard: "like new" and "not new" don't count as "new".
- **Brand:** brand in specifics ≠ a brand token in the title. Also "compatible with X" / "for X" in the title while brand=X, which is a common counterfeit pattern; this one is reported as info, not a contradiction.
- **Size/capacity/model:** numeric unit tokens (e.g. `128GB` vs aspect `Storage Capacity: 256 GB`, `size 10` vs `US Shoe Size: 9`) are normalized and compared.
- **Quantity:** "lot of 3", "x2", "pair" in the title vs a `Number in Pack`/`Quantity` aspect of 1.
- **Description condition text:** "for parts / not working" anywhere while condition is NEW or USED-working.
- Rules only fire when **both sides are present**, so a missing field never produces a flag.
- **Tests:** per rule, one contradicting fixture, one clean fixture and one with the field missing, plus negation cases ("like new", "not used").

### 3.3 Suspicious-signal checks (`checks/signals.py`, `checks/pricing.py`) → HEURISTIC signals
Details in section 4. Inputs: `Listing`, the comparables list, and optional seller stats. Outputs: `list[Signal]`. Tests use boundary values around each threshold, plus a missing-data case that must return `score=None`.

### 3.4 Equivalent-product search (`matching.py` pure, `pipeline.py` orchestration)
The query strategy is built in pure code; `pipeline.py` executes it. See section 4.2 for scoring. Tests use labeled fixture pairs: same GTIN, conflicting capacity, accessory vs device, etc.

### 3.5 Trust scoring and ranking (`trust.py`)
Input: `list[Signal]` plus `list[Flag]`. Output: `TrustScore`. Ranking is in `pipeline.py` and uses the pure `rank()` in `trust.py`. Details in section 4. Tests are hand-computed examples, plus "all missing → Insufficient data".

### 3.6 Report (`report.py`)
- **Markdown** for people and **JSON** (`dataclasses.asdict`) for machines and future UIs.
- Sections:
  1. **Summary**: band, score, confidence, top 3 reasons, data source and timestamp.
  2. **Facts: claim contradictions**: one table per flag with columns field path, value excerpt and listing link.
  3. **Heuristic signals**: each signal with its score, threshold note, inputs (n=…) and evidence.
  4. **Not assessed**: a list of the missing fields and the signals skipped because of them.
  5. **Equivalent listings**: a table with match method, similarity, trust band, total cost and link.
  6. A fixed disclaimer: "Signals, not verdicts."
- Evidence links back via `field_path` + `listing_id`. In the JSON every flag holds the exact path into `raw`.
- **Untrusted text:** listing text is escaped (Markdown/HTML), truncated, and never interpreted. Nothing from a listing is ever executed, followed, or rendered as HTML.

---

## 4. Algorithms

### 4.1 Trust score
Each signal maps evidence to `s ∈ [0,1]` (1 = reassuring) or `None` (can't assess). Weights add to 1.0 across all signals.

| # | Signal | Measures | Evidence | Scoring (initial) | Weight |
|---|---|---|---|---|---|
| S1 | feedback_volume | Track record size | `seller.feedbackScore` | `min(1, log10(fs+1)/3)`, so 0→0, 10→0.35, 100→0.67, 1000+→1 | 0.20 |
| S2 | feedback_rating | Buyer satisfaction | `seller.feedbackPercentage` | ≥99.5→1, 99→0.85, 98→0.6, 97→0.4, <95→0 (linear between) | 0.20 |
| S3 | price_anomaly | Too-good-to-be-true price | `total_cost` vs median of comparables (same condition) | r = total/median. r≥0.8→1, 0.6→0.6, 0.4→0.2, <0.4→0. **None if fewer than 5 comparables** | 0.20 |
| S4 | new_seller_high_value | New account selling expensive goods | feedbackScore, item price, seller's high-value listing count | If fs<20 and (price>$300 or ≥5 active listings >$300): 0.2. If fs<20 only: 0.6. Else 1 | 0.15 |
| S5 | return_terms | Buyer protection offered | `returnTerms.*` | Not accepted→0.4. ≥30 days→1. 14 days→0.8. Buyer-pays reduces by 0.1 | 0.10 |
| S6 | description_quality | Vague, templated or copied text | description text, comparables' descriptions | Too short (<40 words of content)→0.6. Near-duplicate (shingle Jaccard ≥0.8) of a **different seller's** listing→0.3. Else 1 | 0.10 |
| S7 | shipping_terms | Unusual shipping | handling days, location, shipping cost vs comparables | Handling >10 days→0.5. Shipping cost >3× comparables' median→0.6. Else 1 | 0.05 |

S1–S2 can't tell an honest new seller from a bad one, which is why they're weighted, not gating. S4 uses feedback score as a **proxy for account age** because the Browse API likely doesn't expose registration date; the report says so explicitly.

**Combining: transparent weighted average over available signals only**
```
avail    = [s for s in signals if s.score is not None]
coverage = sum(s.weight for s in avail)                    # 0..1
if coverage < 0.5: return Insufficient data (still list the signals we did compute)
base     = sum(s.weight * s.score for s in avail) / coverage   # renormalize
score    = round(100 * base)
# cap: one fact contradiction keeps the score from being "Good"
if any(flag.severity == "high" for flag in fact_flags): score = min(score, 59); caps_applied += [...]
band = Good ≥75 | Mixed 60–74 | Caution <60
confidence = high if coverage ≥0.85 and n_comparables ≥10 else medium if coverage ≥0.65 else low
reasons = the 3 signals with the largest (weight × (1 − score)), each with its evidence
```
**If it proves too crude:** the weakness of a weighted sum is that strengths cancel weaknesses (great feedback hides a price that's 70% too low). The first fix is already in: **caps** for fact contradictions. Next steps, in order: (1) add a cap for an extreme price anomaly (r<0.4); (2) if you later collect labeled examples (your own reviewed verdicts), fit a logistic regression on the same signals so the weights stay interpretable. No ML in v1.

**Choosing thresholds without labeled data:**
1. Start with the domain defaults above. All of them live in `thresholds.py`, each with a comment saying where it came from.
2. In Phase 5, pull a sample of about 200 live listings from 4–5 categories and look at each signal's distribution. Place thresholds at tails (e.g. price ratio at about p5) rather than guessing.
3. **False-positive check:** build a "known good" set (Top Rated sellers with 10k+ feedback). Caution should be rare there (<5%). If it isn't, loosen the thresholds.
4. Hand-review the 20 lowest-scoring listings and record which flags were wrong. That review becomes a regression fixture.

**Missing data:** a signal with missing inputs returns `None`, which drops it from the sum, renormalizes the weights, lowers coverage and confidence, and lists it under "Not assessed". **Never score missing as 0.** Below 50% coverage the tool says "Insufficient data" instead of producing a number.

**Output wording:** "Trust: Mixed (68/100), medium confidence, 6 of 7 signals assessed. Main reasons: price 45% below median of 14 comparable used listings; seller has 12 feedback. Not assessed: seller account age (not provided by eBay API)." Never "scam" or "fraud".

### 4.2 Equivalent-product matching
**Step A, candidate retrieval (query builder, pure):**
1. A valid GTIN → `search?gtin=…`
2. Otherwise an ePID → `search?epid=…`
3. Otherwise brand + MPN → `q="brand mpn"`
4. Otherwise `q` = brand + model + key numeric attributes (capacity or size), limited to the same `category_ids`.

Filter by the same condition class (new vs used). Take ≤100 results and exclude the original seller.

**Step B, pairwise decision (`match(a, b)`):**
```
# 1. identifiers (strongest)
if both have gtin:      return SAME (method=gtin, sim=1.0) if equal(normalize14(a), normalize14(b)) else DIFFERENT
if both have epid:      same rule
if both brand+mpn:      compare normalized (upper, strip non-alnum) → SAME / DIFFERENT
# 2. hard attribute conflicts → DIFFERENT
for attr in [brand, storage_capacity, size, model, color*]:   # *color = soft, lowers sim only
    if both present and normalized values differ: return DIFFERENT (record disagreement)
# 3. fuzzy text
ta, tb = normalize_title(a), normalize_title(b)   # lowercase, unit-normalize "128 gb"→"128gb",
                                                   # drop marketing words: new, free shipping, fast, l@@k, wow, sale
text_sim   = rapidfuzz.token_set_ratio(ta, tb)/100
aspect_sim = agreeing shared aspects / shared aspects (0.5 if none shared)
sim = 0.6*text_sim + 0.4*aspect_sim
accessory guard: one title has "case|cover|charger|box only|for" + the other doesn't → DIFFERENT
sim ≥ 0.85 → LIKELY_SAME, 0.70–0.85 → POSSIBLE (shown separately), else drop
```
Thresholds are tuned on a labeled set of about 40 hand-made fixture pairs, which is cheap to build and also serves as the test suite.

**Ranking equivalents:**
1. Keep matches that are LIKELY_SAME and trust confidence ≥ medium.
2. Show two picks: **cheapest with trust band Good** and **highest trust within +15% of that price**.
3. Then list everything sorted by band, then total cost.

This avoids one opaque blended "price × trust" number.

---

## 5. Phased roadmap
Each phase ends with `pytest` green and `ruff check` clean.

**Phase 1: offline skeleton + consistency (no API key)**
- Build: pyproject, models, `text.py`, `parse.py`, `FixtureSource`, `consistency.py`, a minimal Markdown report and `cli analyze --offline <fixture>`.
- Fixtures: about 8 synthetic getItem JSONs (clean, new-vs-used, capacity mismatch, quantity mismatch, for-parts, missing seller data, restrictive returns, low-feedback high-value), all with clearly fake seller names.
- **Acceptance criteria:**
  - Each fixture parses.
  - Each contradiction fixture produces exactly its expected fact flag, with the right `field_path`s.
  - The clean fixture produces 0 flags, and the missing-field fixture produces 0 flags.
  - The CLI prints a report on Windows.

**Phase 2: heuristic signals + trust score (offline)**
- Build: `signals.py`, `pricing.py`, `thresholds.py`, `trust.py`, plus synthetic search fixtures (15+ comparables).
- **Acceptance criteria:**
  - Each signal has boundary tests and a `None`-on-missing test.
  - The trust score matches hand-computed values for 3 fixtures.
  - Coverage below 0.5 gives "Insufficient data".
  - The fact-flag cap works.
  - The report shows separate Facts, Heuristics and Not assessed sections.

**Phase 3: equivalent matching + ranking (offline)**
- Build: `matching.py`, the query builder, ranking, the report's equivalents section, and about 40 labeled pair fixtures.
- **Acceptance criteria:**
  - The labeled pairs reach ≥95% accuracy, with zero false SAME on the conflicting-attribute pairs.
  - The two picks are computed correctly on fixtures.

**Phase 4: live eBay client (needs keys)**
- Build: `auth.py`, `client.py`, `cache.py`, `EbaySource`, the `.env.example` keys, Sandbox first and then Production.
- **Acceptance criteria:**
  - MockTransport tests cover token refresh, 429 retry and 404.
  - `analyze <real item id>` works end to end with ≤10 calls (logged).
  - One recorded response is scrubbed and added as a regression fixture.
  - Parsed fields are compared against the live JSON and the field list is corrected.

**Phase 5: calibration + false-positive review**
- Build: a sample script, threshold tuning, and the "known good" check.
- **Acceptance criteria:**
  - Caution rate is <5% on the known-good set.
  - Thresholds are updated with comments on how they were chosen.
  - Reviewed mistakes are added as fixtures.

**Explicitly out of scope for v1 (over-engineering for now):**
- A database or web UI
- async or concurrency
- ML models
- A plugin or marketplace registry
- Image analysis (perceptual hashing for stolen photos is a good v2 candidate)
- LLM-based claim extraction
- Other marketplaces

---

## 6. Risks and open questions

**Risks**
- **API terms:** the eBay API License Agreement limits how long data can be stored and how it may be displayed, and production keys require handling **Marketplace Account Deletion notifications** (or a documented opt-out for apps that store no user data). Check both before Phase 4. Keep reports personal and local in v1.
- **Missing seller fields:** account age and total listing count are probably not in the Browse API. Hence S4 relies on a proxy and a seller-filtered search (1 extra call). The Trading API `GetUser` may provide registration date but needs a different auth flow, so that's deferred.
- **Sandbox data is sparse and fake:** realistic testing needs production keys, and fixtures fill the gap until then.
- **False positives unfairly marking sellers:** new honest sellers, clearance pricing, and international sellers with long handling times will all trigger signals. Mitigations: neutral wording, a confidence level, an "Insufficient data" state, caps only for *fact* contradictions, a known-good calibration set, and never publishing seller-level verdicts.
- **Text parsing errors:** negation ("not new"), sarcasm, and multi-language listings. Rules are conservative, prefer missing a flag over a false flag, and are scoped to English/EBAY_US.
- **Untrusted input:** listing text may contain instructions or HTML/JS. We strip and escape it and never execute or follow it. If an LLM is ever added, listing text is passed as quoted data only.
- **Quota:** 5,000 calls/day is plenty for personal use at ≤10 calls per analysis. Caching protects it during development.

**Decided with the owner (2026-10-13):**
- Scope is eBay-only for v1.
- Marketplace is EBAY_US, currency is USD, and text rules are in English.
- **Focus category is consumer electronics** (phones, laptops, headphones). Fixtures, consistency rules (storage capacity, model) and matching are tuned for it first.
- Reports are for the owner only, generated locally. Not a public service.

**Remaining assumptions:**
- Output is Markdown + JSON.
- The Browse API field names above follow eBay's documented schema but **must be verified against a live response in Phase 4**. eBay's docs blocked automated fetching during this research.

**Still open (not blocking Phase 1):**
- Whether to add the Trading API `GetUser` for seller registration date. Decide in Phase 4 after seeing real responses.
- Exact eBay data-retention limits for the cache. Read the License Agreement before Phase 4.

---

## Verification (for the whole plan)
- After each phase: `pytest` and `ruff check .` pass, and `python -m listinglens.cli analyze --offline <fixture>` prints a report whose flags each cite field paths.
- Phase 4: one real item analyzed end to end, with call count logged at ≤10.
- Phase 5: known-good set Caution rate below 5%.

## Sources
- [eBay API call limits](https://developer.ebay.com/develop/get-started/api-call-limits)
- [eBay community: "About API limit calls"](https://community.ebay.com/t5/eBay-APIs-Talk-to-your-fellow/About-API-limit-calls/m-p/34673055)
