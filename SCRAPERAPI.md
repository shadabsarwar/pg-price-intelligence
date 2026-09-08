# ScraperAPI provider

`backend/config.py` loads `backend/.env` by absolute path before collectors are
created. Existing process variables take precedence. Interpolation is disabled;
the key is read only on the backend and is never included in responses or logs.
Restart the backend after changing the file. `.gitignore` excludes local dotenv
files and virtual environments. This project root currently has no `.git`
repository, so tracked-file history cannot be checked here.

## Run

```powershell
cd D:\Projects\pg-price-intelligence\backend
.\venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\venv\Scripts\python.exe -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

In another terminal:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/collectors/providers/status
```

Expected JSON when a nonblank key exists:

```json
{"provider":"ScraperAPI","configured":true,"status":"READY"}
```

Without a key, HTTP 200 returns `configured: false`, `status: NOT_CONFIGURED`.
READY means configured, not an account validation or a LIVE retailer observation.
This route performs no external requests, consumes no provider credits and does
not return credentials. Swagger is available at `/docs`.

## Explicit account verification and tests

```powershell
.\venv\Scripts\python.exe check_scraperapi.py
.\venv\Scripts\python.exe -m unittest discover -s tests -v
```

The diagnostic calls only ScraperAPI's HTTPS `/account` endpoint and emits a
fixed sanitized AUTHENTICATED result or a structured provider error; it never
prints account contents. On 2026-09-06 the configured local key authenticated
successfully. All 32 backend tests passed, including eight provider tests.
Network failure scenarios use synthetic test doubles, not the real key.

## Error contract and access boundary

`ProviderError.as_dict()` returns `provider`, `code`, and a fixed safe `message`.
Codes include MISSING_API_KEY, INVALID_API_KEY (401), PROVIDER_TIMEOUT,
RATE_LIMITED (429), NETWORK_FAILURE, CREDITS_EXHAUSTED (403), PROVIDER_ERROR,
INVALID_RESPONSE, ACCESS_RESTRICTED and APPROVED_SOURCE_REQUIRED. The transport
uses an eight-second socket timeout, bounded reads, verified HTTPS, no redirects
and no application retries. Logs contain only fixed events, codes and byte counts;
no request URLs, exception text, credentials or response bodies are logged.

`ScraperAPIProvider.fetch()` is available for reviewed adapters and accepts only
exact URLs approved in application code. The default approved set is empty.
Review must cover retailer authorization, robots/path rules, permitted use of
ScraperAPI, schemas and retailer rate limits. ScraperAPI may internally retry or
handle challenges; do not enable it for a source where that violates restrictions.
The project does not configure CAPTCHA solving or use it as a fallback for
blocked sites. Returned challenges stop collection.

LuLu retains its existing approval requirements and remains UNAVAILABLE. No
retailer requests were made during verification. Raw provider responses never
become LIVE listings automatically; DEMO data and the dashboard remain unchanged.
An approved retailer-specific parser and validated product identity are still
required for LIVE prices.

References: [ScraperAPI status codes](https://docs.scraperapi.com/ruby/handling-and-processing-responses/api-status-codes)
and [account endpoint](https://docs.scraperapi.com/account-management/credit-usage).
