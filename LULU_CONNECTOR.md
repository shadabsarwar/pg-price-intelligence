# LuLu Qatar connector proof of concept

## Current result

**No real listing was retrieved or verified. No live collection success is claimed.**
The shipped connector makes zero retailer requests. It returns a structured
blocked response while retaining the DEMO catalogue. This is the connector
framework and integration boundary, not a completed live transport or a
production deployment.

On 2026-09-05, the public Qatar homepage, terms and robots file were inspected:

- [Qatar homepage](https://gcc.luluhypermarket.com/en-qa/): the accessible rendering
  showed navigation, search and a loading/location interface, not a reliable
  product feed. No hidden APIs or authenticated sessions were inspected.
- [Terms, section 4.1](https://gcc.luluhypermarket.com/en-qa/termsAndConditions/):
  commercial reuse of site content requires written permission. None is recorded
  for this project.
- [robots.txt](https://gcc.luluhypermarket.com/robots.txt): generic crawlers are
  excluded from search/API paths and q query URLs, among other restrictions. The
  file also specifies a one-second crawl delay. These rules do not establish
  commercial reuse permission.

Website search scraping was therefore not implemented. No CAPTCHA, login,
access-control or anti-bot workaround was attempted. A search-engine result is
not accepted as a live retailer observation.

## Run and test

```powershell
cd D:\Projects\pg-price-intelligence\backend
.\venv\Scripts\python.exe -m uvicorn main:app --reload --log-level info
```

In Swagger at http://127.0.0.1:8000/docs, run `POST /collectors/lulu/search` with:

```json
{"query": "Ariel Liquid Detergent"}
```

Or use PowerShell/curl:

```powershell
'{"query":"Ariel Liquid Detergent"}' | curl.exe -i -X POST http://127.0.0.1:8000/collectors/lulu/search -H "Content-Type: application/json" --data-binary '@-'
Invoke-RestMethod http://127.0.0.1:8000/collectors/status
```

Expected HTTP **503**, not a successful live result:

```json
{
  "listings": [],
  "listings_found": 0,
  "source_platform": "LuLu Qatar",
  "data_status": "ERROR",
  "collected_at": null,
  "errors": [
    {"code": "PERMISSION_REQUIRED", "message": "..."},
    {"code": "ROBOTS_RESTRICTED", "message": "..."},
    {"code": "APPROVED_SOURCE_MISSING", "message": "..."}
  ],
  "integrated_count": 0,
  "unmatched_count": 0
}
```

Status reports BLOCKED, no last successful collection and zero products collected.
`last_attempt_at` is separate and must not be mistaken for collection success.
Blank/oversized queries return 422. Configured adapter deferrals return 429;
failed retrieval or validation returns 503. Existing product and comparison
endpoints continue working.

The existing frontend runs with `npm run dev` from `frontend`. Its only new UI is
a small LuLu availability notice, refreshed every 10 seconds. It says **Live data
currently unavailable** when blocked, failed or stale. DEMO prices keep DEMO
badges. Existing platform tables already display source names and observation
times. Future accepted images populate a missing master image URL, using the
existing image loading/fallback component.

## Architecture and integration

`RetailerListing` is the common collection format in `collectors/base.py`:
product name, optional brand/company/category/size/barcode, current/original price,
QAR currency, product/image URLs, availability, platform product ID, source
platform and actual collection time. Unknown metadata stays null; company is
never guessed from brand names.

`ApprovedLuluSource` is an abstract extension contract. There is **no concrete
approved source, endpoint, parser or authentication implementation**. The default
application constructs `LuluQatarCollector()` without an adapter. There is no
environment switch that enables scraping.

An eventual reviewed adapter must enforce permitted paths, retailer-issued rate
limits, bounded response size, an at-most-eight-second network timeout and strict
schema validation. It must stop on access denial, rate limiting or CAPTCHA and
must not retry around those restrictions. Permission/source references are audit
metadata, not evidence by themselves; the adapter and agreement require review.
No transport claims to implement these missing network details today.

The surrounding connector serializes search requests, applies at least a 60-second
cooldown (or a longer source limit), validates at most 100 results, checks LuLu
Qatar HTTPS product URLs, rejects non-QAR/duplicate/old observations and records
success only for a nonempty validated result. LIVE is assigned only at that
approved-source boundary. This integration path has been tested **only with
explicit synthetic transport doubles in tests**, not against LuLu.

Integration accepts an exact valid GTIN or a reviewed retailer SKU-to-product ID
binding supplied in `LuluCollectionService`. Name similarity is never enough.
Current DEMO barcodes cannot match real GTINs. Unmatched retailer rows remain in
the search response and are counted, without changing master products.

Accepted rows preserve all DEMO entries, updating only the matching real platform
SKU. Failure retains previous real observations/timestamps and marks them ERROR;
it does not replace them with demo observations. Busy/cooldown deferrals do not
invalidate previously retrieved data. Search is not a complete catalogue feed,
so omitted search results do not delete prior offers.

LIVE, VERIFIED, STALE, DEMO and ERROR continue using the existing status model.
Real live observations become STALE after 15 minutes; ordinary verified feed
observations after 24 hours. Current seeded data stays DEMO. Status product count
means the number of rows in the **last successful batch**, not a cumulative total
or number matched to master products. Last-success time/count survive a failed
attempt within the process. This development application is in memory; restart
clears collection state. Multiple production workers would require shared state,
rate limiting and operational controls before deployment.

## Missing before live access can be enabled

1. Written LuLu authorization covering this commercial price-intelligence use,
   data/image reuse and the permitted collection method.
2. A documented retailer-approved Qatar API/feed or explicitly permitted public
   collection route, with permitted paths and access requirements.
3. Actual response schema and real sample responses, Qatar store/location and
   availability semantics, stable SKU identifiers, and agreed rate limits.
4. A concrete transport/parser implementing the approved contract, including
   network timeouts, robots policy where applicable and refusal handling.
5. Verified GTINs or reviewed SKU mappings for the master catalogue.
6. A successful authorized retrieval checked against a real retailer listing.

## Logging and verification

Logs use `uvicorn.error.lulu` and are visible in the backend terminal. Events show
search query length, blocked policy, retailer_requests=0, accepted counts,
unmatched counts and exception class. Raw response bodies, credentials, URLs
containing secrets and arbitrary exception messages are not logged.

All 22 backend tests pass, including eight new LuLu tests. TypeScript and ESLint
pass. The running HTTP endpoint was checked: 503, ERROR, zero listings, null
collection time; status BLOCKED; existing DEMO products unchanged. Query
validation, Swagger, CORS and frontend HTTP rendering were also checked. This
does not establish live retrieval or browser interaction success.

```powershell
cd D:\Projects\pg-price-intelligence\backend
.\venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Files changed in this task

| File | Change |
|---|---|
| `backend/collectors/base.py` | Modified: common retailer listing, search request/result, error and status models. |
| `backend/collectors/lulu_qatar.py` | Modified: blocked-by-default connector, approved-source contract, validation, cooldown, status and logging. |
| `backend/services/lulu_collection.py` | Created: exact identity integration and failure retention. |
| `backend/main.py` | Modified: shared LuLu instance, search/status routes, compatible existing status route. |
| `backend/tests/test_lulu.py` | Created: blocked, validation, synthetic adapter and integration regression tests. |
| `frontend/components/retailer-availability.tsx` | Created: small availability notice with status polling. |
| `frontend/components/product-dashboard.tsx` | Modified: includes availability notice; preserves the dashboard. |
| `LULU_CONNECTOR.md` | Created: inspection evidence, limits, testing instructions and this manifest. |
