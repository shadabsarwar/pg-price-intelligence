# PG Price Intelligence: persistent pipeline

## What changed and why

The original FastAPI process seeded three P&G products from Python and six competitors from a synthetic JSON fixture. Listings lived inside those objects, refreshes replaced current observations, and catalogue writes disappeared on restart. Matching correctly rejected many incompatible products, but could only search the fixture catalogue. The retailer registry was principally an honest UNAVAILABLE response, not a market discovery source.

The application now uses a local SQLite repository, versioned migrations, validated imports, a durable collection queue and persisted match review. Next.js, the dashboard, comparison dialogs, connector diagnostics, policy controls and existing API URLs remain. There was no existing database or authentication implementation to migrate. New write routes require an administrator token. The existing DELETE route archives an identity and retains its history.

Normal startup contains **no demo products or prices**. Catalogue completeness depends on real input; this implementation does not claim a complete P&G Qatar assortment or working access to every retailer.

## Data model

- `companies`, `brands`, `categories`: ownership and taxonomy.
- `products`: family identity, image and description, isolated between demo and non-demo scope.
- `product_variants`: display name, original size, barcode/SKU, normalized size and pack count, category attributes, provenance, verification and archive state. Existing product API IDs represent variants.
- `retailers`, `retailer_products`: market-specific listing identity, source title/URL/image, availability, last-seen time and failure state.
- `price_observations`: append-only price or explicit missing-price observation, QAR, availability, observation time, source and import/collection event IDs. A missing price never becomes zero. Database triggers reject UPDATE and DELETE on observations.
- `competitor_relationships`: candidate IDs, 0–1 rule agreement, reasons, confidence tier, active state and durable reviewer decisions.
- `data_collection_runs`, `data_collection_errors`, `discoveries`: queue, history, partial results, failures and retained original retailer evidence.
- `import_runs`, `import_errors`, `import_rows`: import summary, row errors and original CSV/JSON row content, including dry runs.
- `schema_migrations`: successfully applied SQL versions. Migrations commit atomically; existing files are not deleted.

`001_intelligence.sql` creates the schema; `002_variant_names.sql` adds the variant display name. Identity and prices are separate. The legacy `Product.price` output is now nullable and always null for database products; retailer observations are the authoritative prices.

SQLite supports the current single-host application and thousands of variants without a database service dependency. WAL, transactions, foreign keys, unique identities and query indexes are enabled. This is **not a distributed PostgreSQL implementation**. Multi-host deployment needs a PostgreSQL repository/migration port and an external job worker before scaling out.

## Run locally (PowerShell)

From the project root, prepare the backend if needed:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

The existing `backend/venv` can also be used if it works on your machine. In this development environment its interpreter requires execution outside the sandbox; no replacement environment or dependencies were installed during implementation.

In a separate terminal:

```powershell
cd frontend
npm ci
npm run dev
```

Open `http://localhost:3000`. The API reference is at `http://127.0.0.1:8000/docs`. For production frontend validation, use `npm run build` then `npm run start`. The existing Next.js layout downloads Google fonts during a fresh build, so that build needs network access.

Set `INTELLIGENCE_DB_PATH` in `backend/.env` or the process environment to choose a database file. Set a private random `INTELLIGENCE_ADMIN_TOKEN` there to enable admin writes. Enter that token on `/admin`; the page retains it only in memory. Copy setting names from `.env.pipeline.example`, not an example token. Keep the token out of frontend public environment variables. Run one Uvicorn process/worker with the embedded collection queue.

## Import a complete P&G catalogue

1. Obtain an authorized catalogue or approved feed export. Importing country=QA indicates the supplied catalogue's market scope; actual Qatar availability still requires a retailer listing and observation.
2. Use `backend/data/catalogue-template.csv` (headers only). One row represents one variant, optionally at one retailer. Repeat a variant row for additional retailers.
3. Required fields: `company`, `brand`, `category`, `product_name`. Use `company=P&G` for this import route. Ownership is supplied by the source, not inferred from a brand dictionary.
4. Populate `product_family` consistently to group variants, plus `variant_name`, `size`, `unit`, `pack_count`, `barcode` and `sku` where known. Keep barcodes as text when editing a CSV in a spreadsheet.
5. Supply `subcategory`, `purpose` and a JSON `attributes` object for useful matching. Examples of attribute keys are `form`, `concentration`, `diaper_size`, `razor_type`, `blades`, `target_customer`, `product_type`. Attribute values are strings. In CSV, escape the JSON field using standard CSV quoting.
6. Validate, then import:

```powershell
cd backend
.\venv\Scripts\python.exe manage.py import D:\Catalogues\pg-qatar.csv --kind pg --dry-run
.\venv\Scripts\python.exe manage.py import D:\Catalogues\pg-qatar.csv --kind pg
```

Use your `.venv` path instead if that is the environment you created. CLI CSV input is streamed row by row; JSON arrays are also accepted. Files may contain many thousands of products without changing source code. The admin page accepts CSV/JSON content up to 20 MB, offers a dry run, then imports valid rows and displays individual errors. Larger files should use the CLI.

Incomplete optional data is retained with quality flags. A provided but invalid size/URL/price is an explicit row error, retained in the import report; valid neighboring rows still commit. Dry runs roll back catalogue/listing/price changes but intentionally retain their audit report and original input.

## Import competitors

Use the same columns and real competitor company/brand names:

```powershell
.\venv\Scripts\python.exe manage.py import D:\Catalogues\competitors-qatar.csv --kind competitor --dry-run
.\venv\Scripts\python.exe manage.py import D:\Catalogues\competitors-qatar.csv --kind competitor
```

The equivalent web routes are `POST /imports/products` and `POST /imports/competitors`, with `X-Admin-Token` and JSON `{ "format": "csv", "content": "...", "dry_run": true, "source_state": "IMPORTED" }`. `source_state` may be IMPORTED, MANUAL or DEMO; clients cannot label an upload COLLECTED or VERIFIED. Verification is a separate reviewed operation, and demo identities cannot be verified.

After committed imports the matching engine recalculates candidate relationships. A new competitor needs sufficient category/purpose/quantity/format evidence before becoming an automatic comparison.

## Retailer observations and repeatability

To import a price, include `retailer` and either a stable `retailer_sku` or `product_url`. Supply a positive `price`, `currency=QAR`, and `availability` (`available`, `out_of_stock`, `unknown`). Use an ISO 8601 `observed_at` with timezone. Missing availability remains unknown and is excluded from best-price ranking. A listing may have no price and remains visible in history with MISSING_PRICE.

Identity uses normalized company/brand/family/category/variant, per-item quantity, dimension and pack count. Equivalent units deduplicate. A two-pack remains distinct from one large package even when totals match. Barcode conflicts and retailer-SKU reassignment are reported instead of silently merged. Blank fields do not erase known data. Conflicting identity corrections require a reviewed reconciliation; this version has no bulk identity-merge endpoint.

The same source row is idempotent: it does not append a duplicate price or advance last-seen time. Include a new observation timestamp for a new observation, even when price is unchanged. Each collection run has a separate event ID. Backfilled history is retained without replacing the latest observation. Original rows are retained in `import_rows`, and raw discoveries in `discoveries`.

## Collection architecture

`BaseRetailer` exposes search/search_products, details, category collection and normalization hooks. The existing registry has LuLu, Carrefour and Noon adapters. New adapters return validated `RetailerSearchResult`/`RetailerProduct` objects and enforce their own source permissions, timeouts and rate limits. Unsupported sources return UNAVAILABLE with a reason and no fabricated observations.

LuLu's existing `ApprovedLuluSource` injection contract is bridged into the new queue. **No concrete authorized transport is supplied or activated.** Configure an actual authorized implementation before expecting collection. Existing source-policy and provider diagnostics remain intact. The legacy synchronous search routes remain for compatibility and record results; normal dashboard reads do not perform collection.

Queue work on `/admin` or `POST /collection/run` with `{ "retailers": ["lulu_qatar"], "query": "liquid detergent", "category": "Laundry" }`. Category is operator-provided context when the source lacks it; company/brand are never copied from the search query. Every discovered row is retained. Rows missing reliable identity metadata are placed in review instead of attached to an arbitrary P&G product. Enrich and import those rows using the source evidence and the same retailer URL.

The POST returns run IDs immediately. The lifespan worker claims queued work transactionally and persists each row independently. One retailer's failure does not stop later jobs. Failed/partial/unavailable jobs can be explicitly retried via `POST /collection/{id}/retry`; retry creates another historical run. Interrupted RUNNING jobs become ERROR on worker restart, while QUEUED jobs remain queued. There is no automatic retry around source restrictions or rate limits.

Use an external scheduler to POST collection jobs for scheduled operation. An internal schedule editor, distributed worker ownership and automatic exponential-backoff retries are not implemented. Adapters must obey bounded network operations; a blocking third-party adapter can delay this single worker.

## Matching and unit prices

`data/matching_rules.json` configures weights and thresholds. The retained scoring weights are category 20, subcategory 20, purpose 20, relative size 15, pack count 10, attribute agreement 10 and variant 5 (100 total). Scores are rule agreement, **not calibrated probabilities**. Persisted scores use 0–1; compatibility responses keep 0–100.

High confidence is ≥0.90, likely ≥0.70, possible ≥0.50. Lower scores are not candidates. Automatic matching requires category, subcategory, purpose, compatible unit dimension and essential format attributes. Different diaper sizes, razor types, concentrations, known target-customer/product-type contradictions, same company and same brand are excluded. Quantities differing by more than 4× are excluded. Missing evidence may produce a possible candidate for review; arbitrary category-only products are not direct competitors.

Review decisions survive recalculation. Rejected candidates are removed from the main comparison; approved possible candidates can appear with their explicit explanation. Approval does not invent quantities or prices, so a candidate can still have unavailable unit comparisons. Demo and real identities are kept separate.

Volume is normalized to litres, mass to kilograms, and counts to diapers or razors/refills. Total = per-item quantity × pack count. Prices use QAR/L, QAR/kg or QAR/item; personal/hair/skin-care liquid products and shampoo use QAR/100 ml. Unit conversion uses Decimal while parsing, then calculations are rounded to six decimals. Unknown quantities return null. Currency, availability, freshness and demo isolation govern best-price eligibility; delivery fees are not included.

## Source and quality states

| State | Meaning |
|---|---|
| COLLECTED / LIVE | Facts returned by an approved connector; LIVE is the compatibility freshness label. |
| IMPORTED | Supplied CSV/JSON data, not a live retailer fetch. |
| MANUAL | Operator-entered catalogue data. |
| VERIFIED | An administrator reviewed product identity; this does not verify every price or change its original provenance. |
| DEMO | Synthetic development fixture, opt-in and excluded from production reads. |
| UNAVAILABLE | No approved source or no usable collection result, with an explicit reason. |
| STALE | Collection observations older than 15 minutes, or imported/manual observations older than 24 hours. |
| ERROR | A collection failure; previous observations are retained but excluded from current-price ranking. |

Quality checks expose MISSING_PRICE, MISSING_IMAGE, MISSING_PRODUCT_URL, MISSING_QUANTITY, RETAILER_UNAVAILABLE, NO_COMPETITOR_FOUND, LOW_CONFIDENCE_MATCH, STALE_DATA and COLLECTION_ERROR. The history view includes missing-price listings that the legacy numeric listing contract cannot represent. API polling never makes prices fresher.

## Demo migration and data retention

Use a **separate empty database** for development:

```powershell
$env:INTELLIGENCE_DB_PATH = 'D:\Projects\pg-price-intelligence\backend\data\demo.sqlite3'
$env:INTELLIGENCE_DEMO = '1'
.\venv\Scripts\python.exe manage.py seed-demo
.\venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

The seed migrates the existing three masters and six competitors once, preserving their IDs, and refuses to seed a populated database. Original fixtures are retained. Do not enable DEMO for the production database. The first seed time is a synthetic timestamp, never a claimed retailer collection.

Back up the database with SQLite's backup API or stop the server before copying the database file. A live WAL deployment also has journal files; do not copy only its main file while writes are active. There are no automatic destructive cleanup or history-purge operations.

## API additions and compatibility

Existing products, comparisons, best-price, competitor catalogue, companies/brands, collectors, diagnostics and market-position routes remain. GET products accepts limit/offset/category/q. Public reads expose recorded market facts; new web writes use the admin token. Existing POST `/products` persists a manual identity and ignores the legacy standalone package-price field because it has no retailer identity. DELETE archives instead of deleting observations.

Added: `/products/{id}/prices`, `/retailers`, `/retailers/{id}/products`, `/collection-status`, `/collection-status/{id}`, `/collection/run`, `/collection/{id}/retry`, `/imports/products`, `/imports/competitors`, `/imports`, `/matches`, `/matches/recalculate`, `/matches/{source}/{candidate}/review`, `/products/{id}/verify`, `/quality`, `/discoveries`.

## Validation and limitations

Run `cd backend; .\venv\Scripts\python.exe run_tests.py`. The runner creates and removes a disposable database with explicit demo fixtures for the legacy regression tests. New tests use independent empty databases. Production data is never used by that runner.

Validated during implementation: backend coverage includes all 53 existing tests and 18 new pipeline tests (normalization, unit prices, 1,000-row import, duplicates, row rollback, dry run, retained original input, demo metadata isolation, history, immutable observations, persistence/restart, provenance, quality, scoring/review, connector failures, partial discoveries, token enforcement and API responses). Frontend TypeScript, ESLint and production build are checked separately. Running `/products` and `/admin` returned HTTP 200; the default product response was `[]`. Browser visual testing was unavailable because no browser session was connected. See the final verification record below.

Remaining limits: no complete authorized P&G/competitor catalogue supplied; no activated live retailer transport; single-host SQLite and embedded worker; no enterprise login/RBAC or per-user review attribution; manually curated category/attribute vocabulary; conservative identity reconciliation; synchronous bulk import/match recalculation; dashboard assembles paginated catalogue reads in browser memory (cards render 24 at a time); JSON imports and dry-run evidence use memory proportional to input. There is no deployment or cloud database provisioning in this change.

## Files changed

Added:

- `.gitignore`, `IMPLEMENTATION_PLAN.md`, `PIPELINE_GUIDE.md`
- `backend/.env.pipeline.example`, `backend/manage.py`, `backend/run_tests.py`, `backend/pipeline_api.py`
- `backend/migrations/001_intelligence.sql`, `backend/migrations/002_variant_names.sql`
- `backend/data/demo_products.json`, `backend/data/matching_rules.json`, `backend/data/catalogue-template.csv`
- `backend/services/database.py`, `backend/services/repository.py`, `backend/services/imports.py`, `backend/services/normalization.py`, `backend/services/matches.py`, `backend/services/collection_jobs.py`, `backend/services/demo_migration.py`
- `backend/tests/test_pipeline.py`
- `frontend/app/admin/page.tsx`, `frontend/components/price-history.tsx`

Updated:

- `backend/main.py`
- `backend/models/product.py`, `backend/models/platform_listing.py`
- `backend/services/product_matching.py`, `backend/services/competitor_matching.py`, `backend/services/market_analysis.py`, `backend/services/price_normalization.py`
- `backend/collectors/retailers/base_retailer.py`, `backend/collectors/retailers/lulu_qatar.py`
- `frontend/hooks/use-products.ts`
- `frontend/types/product.ts`, `frontend/types/intelligence.ts`
- `frontend/components/data-status.tsx`, `frontend/components/product-card.tsx`, `frontend/components/product-dashboard.tsx`, `frontend/components/price-comparison.tsx`

Runtime artifacts include the default empty `backend/data/intelligence.sqlite3`, local test output and frontend build/typecheck outputs. Database and build files are ignored. No original fixture, UI route or data file was deleted. The workspace has no Git repository, so this manifest is provided in place of a Git diff.

## Final verification record

- Backend: **71 tests passed** (53 retained regression tests + 18 pipeline tests).
- Frontend: ESLint, TypeScript and the complete Next.js production build passed (all four routes generated).
- Local API and Administration route: HTTP 200; production catalogue empty until import.
- Browser rendering/interactions: not verified; browser discovery returned no available sessions.
