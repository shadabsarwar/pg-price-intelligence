"""Compatibility imports for the original provider path."""
from collectors.providers.scraperapi_provider import (
    NoRedirects, ProviderError, ProviderStatus, ScraperAPIProvider,
)

__all__ = ["NoRedirects", "ProviderError", "ProviderStatus", "ScraperAPIProvider"]
