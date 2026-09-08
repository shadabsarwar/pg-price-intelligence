# Configurable source allowlist

This replaces the former HTTPBin-only diagnostic restriction. No retailer is
implicitly approved, and no API key or local dotenv content was copied or changed.

## Configuration

In `backend/.env`, keep your existing `SCRAPERAPI_KEY` line and add:

```dotenv
APPROVED_RETAILER_DOMAINS=shop.your-retailer.com,products.your-retailer.com
```

Replace these illustrative hostnames with the exact public hosts you are
authorized to collect from using this method. Hostnames are case-insensitive and
IDNA-normalized. Do not include `https://`, paths, ports, wildcards or IP addresses.
Subdomains require separate entries; `shop.example.com` does not approve
`private.shop.example.com` or `shop.example.com.evil.com`. Empty means deny all.
One invalid configuration entry invalidates the allowlist instead of being ignored.

The only required environment variables are:

| Variable | Purpose |
| --- | --- |
| `SCRAPERAPI_KEY` | Existing secret provider credential; unchanged. |
| `APPROVED_RETAILER_DOMAINS` | Comma-separated explicitly approved exact hostnames. |

`backend/.env.example` contains blank safe defaults and comments. Process
environment variables take precedence over dotenv values. Changes to `.env`
require a backend restart. No database or frontend changes are required.

## Restart and test

Stop the backend with **Ctrl+C** in its terminal, then:

```powershell
cd D:\Projects\pg-price-intelligence\backend
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe -m uvicorn main:app --reload --host 127.0.0.1 --port 8000 --log-level info
```

Open http://127.0.0.1:8000/docs and use **POST /collectors/test**:

```json
{"url":"https://shop.your-retailer.com/products/ariel-liquid-detergent"}
```

This is an illustrative request, not a claim that the example host or product
exists. Substitute an actual authorized hostname and public product-page path.
The hostname must be in your allowlist, all DNS answers must be public, robots
must permit the URL, and the page must be directly accessible without credentials
or challenges before a ScraperAPI fetch is attempted.

Successful previews use `data_status: FETCHED`. A preview verifies a page fetch,
not a parsed price, SKU match, or LIVE retailer observation. Errors always use
`success: false`, `data_status: ERROR`, an empty preview and fixed reason. No
failure falls back to DEMO. A failed/unverified final source URL is returned as
null rather than echoing an unsafe submitted URL.

All results contain `provider`, `success`, `status_code`, `source_url`,
`fetched_at`, `content_preview`, `data_status`, `error_code` and `reason`.
`status_code` is an observed upstream HTTP status when available, otherwise null;
the endpoint's own HTTP status reports policy/provider failure independently.

**GET /collectors/providers/status** retains `provider`, `configured`, and
`status`, and adds:

```json
{
  "provider": "ScraperAPI",
  "configured": true,
  "status": "READY",
  "api_key_available": true,
  "approved_domain_count": 2,
  "source_configuration_status": "READY"
}
```

`source_configuration_status` can be READY, EMPTY or INVALID_CONFIGURATION.
Provider READY means the key exists; it does not assert retailer permission or
authentication success. This status route does not perform network requests.

## Enforcement and limits

The shared `SourcePolicy` runs in both the HTTP service and provider. It rejects
non-HTTPS URLs, credentials, sensitive query fields, fragments, non-443 ports,
ambiguous URL syntax, localhost/internal names and IP literals. Every DNS answer
must be globally routable; mixed public/private answers are blocked, including
loopback, link-local, private, shared, multicast and metadata addresses. Unapproved
hosts never trigger DNS, direct requests or ScraperAPI.

Direct access checks use TLS certificate verification and SNI for the approved
hostname while connecting to a previously validated numeric IP, preventing local
DNS rebinding between validation and connection. They ignore environment proxies,
send no credentials or cookies, and never follow redirects. DNS is rechecked
before source and provider requests. ScraperAPI itself resolves the destination
on its infrastructure; local code cannot pin or independently verify the IP it
uses. Only explicitly trusted approved hostnames should be configured.

Robots are retrieved directly and parsed with Protego, including wildcard and
end-anchor rules. Both the project user-agent and generic rules are enforced.
Missing robots (404) is accepted for an explicitly approved source; robots
failures, redirects, HTML error pages and restrictions stop collection. Robots
are cached for at most five minutes. Crawl/request-rate intervals up to eight
seconds are honored between page requests; longer intervals return
SOURCE_RATE_POLICY and require a scheduled connector.

A direct public HTML check must succeed before ScraperAPI is contacted. Login,
paywall and challenge markers, 401/402/403, rate limiting, and redirects stop the
attempt. Detection is conservative and can reject pages that mention CAPTCHA;
it is not an authorization verifier. Configuring a hostname is an operator
assertion of permission, not a way to override publisher restrictions.

The provider uses `follow_redirect=false` and the existing no-redirect HTTP
handler. Returned final URLs undergo the same validation and must match the
requested canonical URL. A redirect destination must be submitted separately.
No rendering, premium proxy, CAPTCHA-solving or other bypass parameters are set.
ScraperAPI's internal infrastructure is controlled by the provider; do not
authorize a source whose permitted method is incompatible with that service.

Network sockets have an eight-second timeout; reads are bounded to 2 MiB (512 KB
for robots). The multi-stage diagnostic can take longer than one socket timeout.
There are no automatic retries. Diagnostics retain a one-per-minute cooldown per
backend process plus per-host checks. Multiple production workers require a
shared limiter before deployment.

Events use `uvicorn.error.scraperapi` and include BLOCKED_BY_ALLOWLIST, FETCHING,
SUCCESS, PROVIDER_ERROR and PARSING_ERROR. They contain fixed codes and statuses,
not URLs, request bodies, credentials or arbitrary exception text. The background
collector status path was also changed to omit arbitrary exception messages.

The existing unavailable retailer search adapters retain their own permission,
schema and product-matching requirements. A domain approval enables this public
page diagnostic; it does not manufacture a retailer parser or change DEMO prices.

## Restriction locations and changed files

Previously `services/provider_test.py` enforced `PUBLIC_TEST_URLS`, while
`collectors/providers/scraperapi_provider.py` independently enforced
`_approved_urls`. Both now use `collectors/source_policy.py`. Existing reviewed
code adapters may still pass exact URLs, but these undergo the same security
checks. Other APPROVED_SOURCE_REQUIRED occurrences in `collectors/lulu_qatar.py`,
`collectors/base.py` and `main.py` concern retailer adapter availability and were
not the cause of the HTTPBin-only test restriction.

Changed/added:

- `backend/collectors/source_policy.py`
- `backend/collectors/public_access.py`
- `backend/collectors/providers/errors.py`
- `backend/collectors/providers/base_provider.py`
- `backend/collectors/providers/scraperapi_provider.py`
- `backend/services/provider_test.py`
- `backend/services/market_refresh.py`
- `backend/requirements.txt`
- `backend/.env.example`
- `backend/tests/test_source_policy.py`
- `backend/tests/test_live_collection.py`
- `backend/tests/test_scraperapi.py`
- `SOURCE_ALLOWLIST.md`

Validation: all 53 backend tests passed, including a synthetic approved-domain
product-page request through the HTTP route, DNS/SSRF tests, robots wildcard
denials, access challenges, redirect checks, log redaction and legacy regressions.
No real retailer was queried or newly declared LIVE during this change.

Reference: ScraperAPI documents the
[follow_redirect parameter](https://docs.scraperapi.com/control-and-optimization).
This document supersedes the HTTPBin-only configuration described in older phase
notes; their historical test results remain historical.
