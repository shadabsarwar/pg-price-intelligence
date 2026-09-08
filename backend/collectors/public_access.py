"""Direct, TLS-verified, DNS-pinned public checks before any proxy request."""
import http.client
import socket
import ssl
import threading
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

from protego import Protego

from collectors.providers.errors import ProviderError
from collectors.source_policy import ApprovedTarget, SourcePolicy

USER_AGENT = "PGPriceIntelligence"


def reject_restrictions(body: bytes, status: int = 200):
    lowered = body.lower()
    if any(marker in lowered for marker in (b"captcha", b"access denied", b"verify you are human",
            b"sign in to continue", b"login required", b"authentication required", b"subscribe to continue",
            b'"isaccessibleforfree":false', b'"isaccessibleforfree": false',
            b'type="password"', b"type='password'")):
        raise ProviderError("ACCESS_RESTRICTED", status)


@dataclass(frozen=True)
class PublicResponse:
    status: int
    body: bytes
    content_type: str


def direct_get(target: ApprovedTarget, limit: int = 2 * 1024 * 1024) -> PublicResponse:
    if not target.addresses:
        raise ProviderError("SSRF_BLOCKED")
    connection = http.client.HTTPSConnection(target.hostname, timeout=8, context=ssl.create_default_context())
    # Connect to the validated numeric address, while HTTPSConnection retains the
    # approved hostname for certificate verification, SNI and the HTTP Host header.
    # No second hostname lookup, environment proxies, redirects, cookies or auth.
    connection._create_connection = lambda address, timeout, source_address=None: socket.create_connection(
        (target.addresses[0], 443), timeout, source_address)
    try:
        parsed = urlsplit(target.url)
        path = parsed.path + ("?" + parsed.query if parsed.query else "")
        connection.request("GET", path, headers={"User-Agent": USER_AGENT, "Accept": "text/html,text/plain"})
        response = connection.getresponse()
        body = response.read(limit + 1)
        if len(body) > limit:
            raise ProviderError("PARSING_ERROR", response.status)
        return PublicResponse(response.status, body, response.getheader("Content-Type", "").lower())
    except (TimeoutError, socket.timeout):
        raise ProviderError("PROVIDER_TIMEOUT") from None
    except (OSError, http.client.HTTPException, UnicodeError, ValueError):
        raise ProviderError("NETWORK_FAILURE") from None
    finally:
        connection.close()


class PublicAccessGuard:
    def __init__(self):
        self._lock = threading.Lock()
        self._last = {}
        self._delay = {}
        self._robots = {}

    def check(self, policy: SourcePolicy, target: ApprovedTarget):
        with self._lock:
            now = time.monotonic()
            delay = self._delay.get(target.hostname, 60)
            if now - self._last.get(target.hostname, float("-inf")) < delay:
                raise ProviderError("RATE_LIMITED")
            self._last[target.hostname] = now
            cached = self._robots.get(target.hostname)
        if cached and now - cached[0] < 300:
            rules = cached[1]
        else:
            # Only robots.txt, on the same already-validated host/address.
            robots = direct_get(ApprovedTarget("https://" + target.hostname + "/robots.txt",
                                              target.hostname, target.addresses), limit=512000)
            if robots.status == 404:
                rules = Protego.parse("")
            elif robots.status == 200:
                reject_restrictions(robots.body)
                if b"<html" in robots.body.lower() or b"<!doctype html" in robots.body.lower():
                    raise ProviderError("ROBOTS_UNAVAILABLE")
                try:
                    rules = Protego.parse(robots.body.decode("utf-8-sig"))
                except (ValueError, UnicodeError):
                    raise ProviderError("ROBOTS_UNAVAILABLE") from None
            else:
                raise ProviderError("ROBOTS_UNAVAILABLE", robots.status)
            with self._lock:
                self._robots[target.hostname] = (now, rules)
        if not rules.can_fetch(target.url, USER_AGENT) or not rules.can_fetch(target.url, "*"):
            raise ProviderError("ROBOTS_RESTRICTED")
        crawl_delay = max(float(rules.crawl_delay(USER_AGENT) or 0), float(rules.crawl_delay("*") or 0))
        rate = rules.request_rate(USER_AGENT) or rules.request_rate("*")
        if rate and rate.requests:
            crawl_delay = max(crawl_delay, rate.seconds / rate.requests)
        # Honor short publisher intervals between direct checks and provider fetch.
        # Longer intervals require a scheduled connector rather than blocking here.
        if crawl_delay > 0:
            with self._lock:
                self._delay[target.hostname] = max(60, crawl_delay)
            if crawl_delay > 8:
                raise ProviderError("SOURCE_RATE_POLICY")
            time.sleep(crawl_delay)
        target = policy.validate(target.url)  # DNS recheck immediately before access.
        page = direct_get(target)
        if 300 <= page.status < 400:
            raise ProviderError("REDIRECT_BLOCKED", page.status)
        if page.status in {401, 402, 403}:
            raise ProviderError("ACCESS_RESTRICTED", page.status)
        if page.status == 429:
            raise ProviderError("RATE_LIMITED", 429)
        if page.status != 200:
            raise ProviderError("PROVIDER_ERROR", page.status)
        reject_restrictions(page.body, page.status)
        if not page.content_type.startswith(("text/html", "application/xhtml+xml")):
            raise ProviderError("PARSING_ERROR", page.status)
        if crawl_delay:
            time.sleep(crawl_delay)
