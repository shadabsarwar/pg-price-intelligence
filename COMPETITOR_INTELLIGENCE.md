# Competitor intelligence implementation

The existing dashboard and platform-price modal remain available. Click a product
name or **Compare Competitors** to open the intelligence view. It defaults to the
Competitors tab; Overview, Platform Prices and Price History are also available.
The Price History tab explicitly explains that history is not stored yet.

## Run

Use two PowerShell terminals. Do not start duplicate servers if already running.

```powershell
cd D:\Projects\pg-price-intelligence\backend
.\venv\Scripts\python.exe -m uvicorn main:app --reload
```

```powershell
cd D:\Projects\pg-price-intelligence\frontend
npm run dev
```

Dashboard: http://127.0.0.1:3000
API documentation: http://127.0.0.1:8000/docs

## Data and configuration

All seeded specifications, quantities, offers, availability and observation times
are **DEMO**. No live retailer connection has been configured. There are six
competitor SKUs: Persil 2L and 4L, Surf 2L, Huggies size 4 in two pack counts, and a
Schick refillable razor. Each has three synthetic platform listings.

The illustrative Pampers pack count is 48; it is not a verified specification for
the original sample SKU. Product images remain absent unless a source supplies a
URL. No fake image URLs or retailer product links were added.

Edit `backend/data/competitor_catalogue.json` to add companies, brands, structured
master attributes and competitor fixtures. Each brand references a company ID;
each competitor references a brand ID. Duplicate product IDs and missing company
references fail at startup. Restart the backend after editing JSON: standard
Uvicorn reload does not necessarily watch JSON. No company or brand is hard-coded
into the matching algorithm. Products created through the existing POST endpoint
can supply the new optional attributes; incomplete old payloads still work but
will not yield guessed matches.

Regional brand mappings need care. The Persil demo uses Henkel based on
[Henkel's GCC brand page](https://www.henkel-gcc.com/en/brands-and-businesses/persil-656482).
Other reference sources are stored with the brands:
[Surf / Unilever Professional](https://www.unileverprofessional.com.au/au/en/brands/surf/),
[Huggies / Kimberly-Clark](https://www.kimberly-clark.com/en-us/), and
[Schick / Edgewell](https://edgewell.com/pages/our-brands).
Brand affiliation does not verify a sample SKU's Qatar availability or price.

## Matching and confidence

Candidates must have different company and brand identities, identical normalized
category, subcategory and purpose, compatible quantity dimensions, and matching
essential attributes. Liquid/weight products require form and concentration;
diapers require form and diaper size; razors require form and razor type.
Missing essential values produce no match. Total quantity must be within a 4:1
ratio. This is a transparent rule-based baseline, not AI or a probability model.

| Contribution | Maximum | Rule |
|---|---:|---|
| Category | 20 | Required exact match, ignoring case/extra whitespace |
| Subcategory | 20 | Required exact match |
| Purpose | 20 | Required exact match |
| Size | 15 | 15 × smaller total quantity / larger total quantity |
| Pack quantity | 10 | 10 × smaller count / larger count |
| Attributes | 10 | 10 × equal attributes / union of attribute keys |
| Variant | 5 | Same known variant |

The total is 0–100, shown with its breakdown. With the synthetic fixtures, Ariel
versus Persil 2L scores 100, Surf 2L scores 95 and Persil 4L scores 92.5. High scores
describe agreement with entered attributes, not confirmed commercial equivalence.

## Normalization and market position

`size_value` is quantity **per item** and `pack_quantity` is the number of items.
Total content = size_value × pack_quantity, converted from ml to L or g to kg.
For diapers/razors use size_value=1 and unit=diaper/razor, then the actual item count.
The original free-text `size` is retained for display; quantities are never parsed
or guessed from product names.

Prices normalize to QAR/L, QAR/kg, QAR/diaper or QAR/razor. Products whose
subcategory is Shampoo normalize to QAR/100 ml. Missing quantities yield null
values, not zero. A 2L product at 25 QAR is 12.50 QAR/L; a 4L product at 40 QAR is
10 QAR/L despite the higher package price.

Available fresh observations in the product's currency determine best/highest
prices. Verified and demo observations are not ranked together. Stale/error
observations and mixed currencies are excluded. Competitor-versus-P&G differences
include both package and normalized differences. Difference = competitor − P&G;
percentage = difference / P&G × 100. A zero baseline yields a null percentage.

Market average uses the best normalized price of each eligible competitor product,
excluding the P&G product. Market position = (P&G unit price − competitor unit
average) / competitor unit average × 100. Ties receive the same highlights.
Cheapest/most-expensive package, closest attribute match, and best unit value are
labeled separately. Delivery charges and promotions outside the listing price
are not modeled.

## Status and refresh

| Status | Meaning |
|---|---|
| DEMO | Synthetic observation; never promoted by dashboard polling |
| LIVE | Verified observation from an approved live collector, at most 15 minutes old |
| VERIFIED | Verified feed observation, at most 24 hours old |
| STALE | Verified observation older than its configured freshness window |
| ERROR | Collection failure, invalid future timestamp, or no product observations |

These windows are development defaults in `models/platform_listing.py`. Product
status conservatively reflects verified observations when present: any error or
stale observation makes the aggregate ERROR/STALE. Source-level status and last
successful observation time remain visible alongside the platform name.

Frontend polling runs every 10 seconds. The intelligence view has its own polling
and retains the last successful response on a transient error, clearly indicating
the API failure. API refresh time is separate from listing observation time.

The backend lifespan worker checks enabled adapters every 10 seconds after the
previous cycle completes. No adapters are enabled initially. `/collectors` reports
NOT_CONFIGURED with an explanation, not invented live prices. To integrate an
approved source, implement `collect(product)` with exact SKU matching and network
timeouts, set the adapter platform and enabled flag, and register it with
`MarketRefresher`. Return validated `PlatformListing` observations for that platform
with verified provenance, actual observation timestamps and source names.
Collection failure preserves previous observations and marks them ERROR.
Empty successful results remove previous verified offers for that platform.
Demo fixtures remain separate. Everything is in memory and resets on restart.

## Endpoints

Existing root, product CRUD and platform comparison endpoints remain available.

- `GET /products/{id}/competitors`: matched competitors with score and price metrics.
- `GET /products/{id}/competitor-comparison`: full P&G/competitor/market response.
- `GET /products/{id}/market-position`: normalized market summary.
- `GET /competitors`: separate competitor catalogue.
- `GET /companies` and `GET /brands`: configured registry.
- `GET /collectors`: adapter configuration and last successful refresh status.

## Files changed in this upgrade

| File | Change and purpose |
|---|---|
| `backend/main.py` | Modified: registers catalogue, intelligence routes and background worker; preserves original routes. |
| `backend/models/product.py` | Modified: optional structured attributes and aggregate data status; re-exports listing type for compatibility. |
| `backend/models/platform_listing.py` | Created: shared listing model, provenance and computed freshness status. |
| `backend/models/company.py` | Created: company registry model. |
| `backend/models/brand.py` | Created: company-linked brand model and ownership reference. |
| `backend/models/intelligence.py` | Created: typed competitor and market API responses. |
| `backend/data/competitor_catalogue.json` | Created: configurable companies, brands, attributes and six competitor fixtures. |
| `backend/services/catalogue.py` | Created: loads/validates the registry and attaches synthetic listings. |
| `backend/services/product_matching.py` | Created: equivalence gates and explainable score. |
| `backend/services/competitor_matching.py` | Created: candidate selection and score ordering. |
| `backend/services/price_normalization.py` | Created: total content conversion and unit-price calculations. |
| `backend/services/market_analysis.py` | Created: price metrics, deltas, ranking and market position. |
| `backend/services/market_refresh.py` | Created: adapter scheduling, validation and failure retention. |
| `backend/services/comparison.py` | Modified: excludes stale/error offers from existing price ranking. |
| `backend/collectors/base.py` | Modified: platform identity and explicit enabled flag. |
| `backend/collectors/carrefour_qatar.py` | Modified: identifies its platform; remains unconfigured. |
| `backend/collectors/lulu_qatar.py` | Modified: identifies its platform; remains unconfigured. |
| `backend/collectors/other_platforms.py` | Created: extension point for additional approved sources. |
| `backend/tests/test_intelligence.py` | Created: eight regression tests covering matching, normalization, status, APIs and collection failure. |
| `frontend/types/product.ts` | Modified: optional structured attributes and source statuses. |
| `frontend/types/intelligence.ts` | Created: intelligence response types and runtime validation. |
| `frontend/hooks/use-intelligence.ts` | Created: cancellable polling, timeout, validation and error handling. |
| `frontend/lib/comparison.ts` | Modified: excludes stale/error platform prices. |
| `frontend/components/data-status.tsx` | Created: consistent five-state badges. |
| `frontend/components/competitor-intelligence.tsx` | Created: accessible native dialog, keyboard tabs, market summary, comparison table and nested platform view. |
| `frontend/components/product-dashboard.tsx` | Modified: opens the new view without replacing the catalogue. |
| `frontend/components/product-card.tsx` | Modified: clickable product title, competitor button and source status. |
| `frontend/components/price-comparison.tsx` | Modified: source names and freshness/error badges in the existing table. |
| `COMPETITOR_INTELLIGENCE.md` | Created: this implementation guide and complete change manifest. |

## Verification

14 backend tests pass (six existing, eight new):

```powershell
cd D:\Projects\pg-price-intelligence\backend
.\venv\Scripts\python.exe -m unittest discover -s tests -v
```

Frontend TypeScript and ESLint checks pass. Actual API responses validate and render
through the competitor table, market summary and existing platform components:
Ariel has three competitors, Pampers two, Gillette one, and each competitor has
three platform rows. The competitor button handler was exercised in a component
check. Dashboard HTTP, API routes, Swagger and CORS were checked.

No browser was available for interactive visual verification. Physical click flow,
native dialog focus, keyboard interaction and responsive layout still need a
browser check. To check manually: open the dashboard, click Compare Competitors,
switch tabs, inspect View Platform Prices, then close both dialogs. Confirm that
the original Compare Prices action still works and demo labels remain visible.
