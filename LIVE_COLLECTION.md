# Live collection phase — 2026-09-06

## Verified result

The real ScraperAPI request to `https://httpbin.org/html` succeeded with HTTP 200
at `2026-09-06T16:27:39.695520Z`. The final URL header matched that source and the
API returned a 300-character plain-text preview. This is a connection test, not
a retailer product or a LIVE price. No retailer returned real product data.

LuLu Qatar, Carrefour Qatar and Noon Qatar each returned UNAVAILABLE, empty
products, null collection timestamp and zero retailer collection requests.
The live-comparison endpoint returned UNAVAILABLE with no demo offers.

## Swagger steps

Open http://127.0.0.1:8001/docs (the explicitly restarted backend).
The existing development backend at http://127.0.0.1:8000/docs also reloaded the
new routes and remains the frontend's default API address.

1. `GET /collectors/providers/status` — Execute; configured key gives READY.
2. Under **Live collection**, open `POST /collectors/test`, click **Try it out**,
   and execute:

   ```json
   {"url":"https://httpbin.org/html"}
   ```

   Expected success includes `status_code: 200`, `source_url`, `fetched_at`, and
   `content_preview`. Calls are limited to one per minute per backend process.
   READY is local configuration only; this POST actually tests the provider.
3. Open `POST /collectors/{retailer}/search`. Set `retailer` to `lulu_qatar` and
   execute:

   ```json
   {"query":"Ariel Liquid Detergent"}
   ```

   Repeat using `carrefour_qatar` and `noon_qatar`. All currently return HTTP 200
   with `data_status: UNAVAILABLE` and a specific reason. HTTP 200 indicates a
   completed availability check, not collection success. Unknown retailer IDs
   return 404; invalid search queries return 422.
4. Execute `GET /products/{product_id}/live-comparison` with `product_id: 1`.
   No permitted live observations are available; offers remain empty.

The old `POST /collectors/lulu/search` contract remains unchanged for existing
consumers. Use `lulu_qatar` on the new generic route for the standardized contract.

## Source review

| Platform | Result | Evidence / missing requirement |
| --- | --- | --- |
| LuLu Qatar | UNAVAILABLE | [Terms §4.1](https://gcc.luluhypermarket.com/en-qa/termsAndConditions/) limits commercial reuse without written permission; none is configured. [Robots](https://gcc.luluhypermarket.com/robots.txt) restricts search/API paths. |
| Carrefour Qatar | UNAVAILABLE | [Terms URL](https://www.carrefourqatar.com/mafqat/en/terms-and-conditions) could not be retrieved in this review. A permitted collection route/feed has not been verified. This is an unverified-permission result, not a claim that all public access is forbidden. |
| Noon Qatar | UNAVAILABLE | [Qatar terms](https://www.noon.com/qatar-en/terms-of-sale/) restrict crawling/scraping. No separately authorized Qatar feed is configured. |

LuLu was the first Qatar platform reviewed; its permission restrictions prevented
a legitimate product collection test. No restricted retailer page was sent to
ScraperAPI. The alternative named retailers also lack a verified permitted feed.
Public visibility or a provider subscription does not grant collection rights.

## Architecture and security

- `collectors/providers/base_provider.py`: provider contract and fetch metadata.
- `collectors/providers/scraperapi_provider.py`: existing implementation moved
  here, now returning HTTP status, final-source header and fetch time. The old
  `collectors/scraperapi.py` path remains a compatibility import.
- `collectors/retailers/base_retailer.py`: standard product/result models with
  nullable unknown facts. Success requires observations and timestamps; no DEMO
  values are accepted by this live result contract.
- `collectors/retailers/{lulu_qatar,carrefour_qatar,noon_qatar}.py`: explicit
  unavailable connectors with reviewed reasons. No fictional parsers or prices.
- `services/provider_test.py`: public diagnostic allowlist, cooldown and redacted
  preview. Arbitrary/private URLs, credentials, query strings and unreviewed
  retailer URLs are denied before network access. Only HTTPBin's static test
  page is approved. No request headers are echoed.
- `services/live_comparison.py`: existing verified live observations only;
  preserves their original timestamps and stale state. Demo rows are excluded.
  Existing demo comparisons continue on their original endpoint.
- `components/live-comparison.tsx`: both product dialogs request the live API
  when opened. P&G and competitor tables include images, platform, prices,
  unit prices, availability, observation time and status. Empty states show
  UNAVAILABLE rather than copying development prices.

ScraperAPI final-source headers are checked against the approved URLs. Missing
final URL metadata fails the diagnostic rather than guessing. Provider redirects
are disabled; no API URL is returned. Errors contain fixed messages and optional
HTTP status, never raw bodies or exception strings. Timeouts, invalid key,
missing key, credit exhaustion, rate limits, network failures and challenges
remain structured failures. No automatic application retries, login, CAPTCHA
solving or security workarounds were added.

The transport alone does not make a retailer live. A permitted source, its schema,
a reviewed parser, source-specific rate limits and exact product identity bindings
are still required. Newly implemented retailer adapters would also need their
observations integrated into the validated comparison store. Current connectors
intentionally have no such unverified transport or integration.

## Validation and runtime

All 40 backend tests passed; TypeScript and ESLint passed. Real HTTP tests covered
the provider fetch, three unavailable collection results and live comparison.
Backend port 8001 was restarted. The frontend was started on port 3000; browser
interaction/visual QA was unavailable because no browser connection was exposed.

```powershell
cd D:\Projects\pg-price-intelligence\backend
.\venv\Scripts\python.exe -m unittest discover -s tests -v
# To start a backend if it is not already running:
.\venv\Scripts\python.exe -m uvicorn main:app --reload --port 8000
```

```powershell
cd D:\Projects\pg-price-intelligence\frontend
npx.cmd tsc --noEmit
npm.cmd run lint
# To start the frontend if it is not already running:
npm.cmd run dev
```

Open http://127.0.0.1:3000 and select a product name, **Compare Prices**, or
**Compare Competitors**. The new section explains live source availability;
the existing development comparisons keep blue DEMO badges. LIVE is green,
STALE yellow, and UNAVAILABLE red.
