"""Fixed public error messages; never attach arbitrary URLs or exception text."""
ERRORS = {
    "MISSING_API_KEY": "ScraperAPI is not configured.",
    "INVALID_API_KEY": "ScraperAPI rejected the API key.",
    "PROVIDER_TIMEOUT": "ScraperAPI request timed out.",
    "RATE_LIMITED": "Source or provider cooldown is active; try again later.",
    "NETWORK_FAILURE": "Unable to connect to the source or ScraperAPI.",
    "CREDITS_EXHAUSTED": "ScraperAPI access denied or account credits exhausted.",
    "PROVIDER_ERROR": "ScraperAPI returned an unsuccessful response.",
    "INVALID_RESPONSE": "ScraperAPI returned invalid or oversized response data.",
    "ACCESS_RESTRICTED": "Authentication, a challenge, or an access restriction was detected; collection stopped.",
    "APPROVED_SOURCE_REQUIRED": "Hostname is not approved. Add its exact hostname to APPROVED_RETAILER_DOMAINS only after confirming permission for this collection method.",
    "INVALID_SOURCE_CONFIGURATION": "APPROVED_RETAILER_DOMAINS must contain comma-separated public hostnames only, without URLs, wildcards, ports or IP addresses.",
    "INVALID_URL": "Use an HTTPS URL on port 443 without credentials, fragments or sensitive query parameters.",
    "SSRF_BLOCKED": "Local, internal, metadata and non-public network destinations are blocked.",
    "ROBOTS_RESTRICTED": "robots.txt disallows this URL; no provider request was made.",
    "ROBOTS_UNAVAILABLE": "robots.txt could not be verified; no provider request was made.",
    "REDIRECT_BLOCKED": "Redirects are disabled. Submit the final permitted public URL explicitly.",
    "PARSING_ERROR": "The source did not return a readable public HTML page; no preview was accepted.",
    "SOURCE_RATE_POLICY": "This source requires a crawl interval longer than this synchronous diagnostic supports; use a scheduled approved connector.",
}


class ProviderError(Exception):
    def __init__(self, code: str, status_code: int | None = None):
        self.code = code
        self.status_code = status_code
        self.message = ERRORS[code]
        super().__init__(self.message)

    def as_dict(self):
        return {"provider": "ScraperAPI", "code": self.code, "message": self.message}
