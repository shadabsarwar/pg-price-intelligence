"""Explicit account-only verification; safe fixed-schema output, no retailer calls."""
import json

from config import load_environment
from collectors.scraperapi import ProviderError, ScraperAPIProvider


if __name__ == "__main__":
    load_environment()
    try:
        print(json.dumps(ScraperAPIProvider().verify_account()))
    except ProviderError as error:
        print(json.dumps(error.as_dict()))
        raise SystemExit(1)
