"""Explicit host approval plus public-network validation; no implicit subdomains."""
import ipaddress
import os
import re
import socket
from dataclasses import dataclass
from urllib.parse import parse_qsl, unquote, urlsplit, urlunsplit

from collectors.providers.errors import ProviderError
from config import scraperapi_key

INTERNAL_SUFFIXES = (".localhost", ".local", ".internal", ".lan", ".home", ".test", ".invalid", ".arpa")
SENSITIVE_QUERY = re.compile(r"(?i)(key|token|secret|password|passwd|auth|credential|signature|session|cookie)")


def public_host(value: str) -> str:
    try:
        host = value.lower().encode("idna").decode("ascii")
    except UnicodeError:
        raise ProviderError("INVALID_URL") from None
    if host.endswith(".") or len(host) > 253 or not re.fullmatch(r"[a-z0-9-]+(?:\.[a-z0-9-]+)+", host):
        raise ProviderError("SSRF_BLOCKED")
    if any(not label or len(label) > 63 or label.startswith("-") or label.endswith("-") for label in host.split(".")):
        raise ProviderError("INVALID_URL")
    if host.endswith(INTERNAL_SUFFIXES) or host in {"metadata.google.internal", "metadata.azure.internal"}:
        raise ProviderError("SSRF_BLOCKED")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ProviderError("SSRF_BLOCKED")
    # Reject legacy integer/octal/hex IPv4 host representations as well.
    if all(re.fullmatch(r"(?:0x[0-9a-f]+|[0-9]+)", label) for label in host.split(".")):
        raise ProviderError("SSRF_BLOCKED")
    return host


def public_address(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    if not address.is_global or address.is_multicast or address.is_reserved or value == "168.63.129.16":
        return False
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped:
            return public_address(str(address.ipv4_mapped))
        if address.sixtofour or address.teredo:
            return False
    return True


@dataclass(frozen=True)
class ApprovedTarget:
    url: str
    hostname: str
    addresses: tuple[str, ...] = ()


class SourcePolicy:
    def __init__(self, domains: frozenset[str]):
        try:
            self.domains = frozenset(public_host(value) for value in domains)
        except ProviderError:
            raise ProviderError("INVALID_SOURCE_CONFIGURATION") from None

    @classmethod
    def from_environment(cls):
        raw = os.environ.get("APPROVED_RETAILER_DOMAINS", "")
        return cls(frozenset(value.strip() for value in raw.split(",") if value.strip()))

    def validate(self, url: str, *, resolve: bool = True) -> ApprovedTarget:
        # Reject ambiguous URL parser interpretations and user-supplied credentials.
        if len(url) > 4096 or any(ord(char) < 33 or ord(char) == 127 for char in url) or "\\" in url:
            raise ProviderError("INVALID_URL")
        key = scraperapi_key()
        if key and key in unquote(url):
            raise ProviderError("INVALID_URL")
        try:
            parsed = urlsplit(url)
            if (parsed.scheme != "https" or not parsed.hostname or parsed.port not in {None, 443}
                    or parsed.username is not None or parsed.password is not None or parsed.fragment):
                raise ProviderError("INVALID_URL")
            host = public_host(parsed.hostname)
            if "%" in parsed.netloc:
                raise ProviderError("INVALID_URL")
            query = parse_qsl(parsed.query, keep_blank_values=True, max_num_fields=100)
            if any(SENSITIVE_QUERY.search(unquote(key)) for key, _ in query):
                raise ProviderError("INVALID_URL")
        except (ValueError, UnicodeError):
            raise ProviderError("INVALID_URL") from None
        if host not in self.domains:
            raise ProviderError("APPROVED_SOURCE_REQUIRED")
        normalized = urlunsplit(("https", host, parsed.path or "/", parsed.query, ""))
        addresses = ()
        if resolve:
            try:
                answers = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
                addresses = tuple(sorted({answer[4][0] for answer in answers}))
            except OSError:
                raise ProviderError("NETWORK_FAILURE") from None
            if not addresses or not all(public_address(address) for address in addresses):
                raise ProviderError("SSRF_BLOCKED")
        return ApprovedTarget(normalized, host, addresses)
