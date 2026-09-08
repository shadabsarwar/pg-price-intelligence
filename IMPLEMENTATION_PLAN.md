# Pipeline audit and implementation plan

## Audit (2026-09-08)

- Frontend: Next.js 16.3.4 App Router, React 19, Tailwind 4. Dashboard, comparison dialogs, connector page, abortable polling hooks and response guards are already implemented.
- Backend: FastAPI/Pydantic, no database, migration framework, authentication or admin system. `/products` uses a mutable dictionary; POST/DELETE disappear on restart.
- Demo: three masters in `main.py`, `data/demo_listings.json`, and six synthetic competitors in `data/competitor_catalogue.json`. Fixture load time becomes the apparent observation time.
- Matching: strict category/subcategory/purpose/essential attribute filters and quantity comparison are valuable, but only search seeded candidates. Scores are embedded in Python; no persisted review state.
- Collection: preserve source allowlist, robots/access policy, timeouts, provider diagnostics, LuLu feed support and retailer registry. Several adapters intentionally return UNAVAILABLE. Legacy refresh mutates product objects and loses historical observations.
- Preserve all existing public routes and UI components. Add provenance without interpreting an API poll as a fresh price collection. No data files will be deleted.
- Baseline tests could not initially start: the checked-in virtual environment points at a missing/inaccessible Windows Store interpreter. Resolve the test runtime separately.

## Implementation sequence

1. Add versioned, transactional SQLite schema (no existing PostgreSQL/Supabase configuration) behind a repository. Separate families, variants, listings and immutable price observations. Index catalogue and time-series queries. Keep compatibility product IDs as variant IDs.
2. Add validated CSV/JSON imports, row savepoints, dry runs, stable identity/deduplication, import audit records and explicit demo migration. Default production database starts empty.
3. Extend the existing connector registry with durable background jobs, isolated retailer failures and retained raw discoveries requiring identity enrichment when incomplete.
4. Persist configurable competitor scores/reasons and review decisions; use database category candidates. Reuse established safeguards for incompatible formats and units.
5. Route the existing APIs to persistence. Add history, collection, import, quality and verification APIs plus a small admin page and history panel. Preserve dashboard layout.
6. Exercise normalization, imports, duplicate handling, jobs, missing data, provenance, history, compatibility routes and frontend checks. Document operations, migration and remaining production limits.

SQLite is the supported initial single-host deployment, not a claim of distributed scalability. A future PostgreSQL deployment requires a repository/migration port and external workers; no cloud database credentials are present.
