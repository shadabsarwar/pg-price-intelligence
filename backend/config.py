"""Load only the backend environment file; never serialize credentials."""
import os
from pathlib import Path

from dotenv import load_dotenv


ENV_FILE = Path(__file__).resolve().parent / ".env"


def load_environment(path: Path = ENV_FILE) -> None:
    # Explicit process configuration wins. No variable interpolation of secrets.
    load_dotenv(path, override=False, interpolate=False, encoding="utf-8-sig")


def scraperapi_key() -> str:
    return os.environ.get("SCRAPERAPI_KEY", "").strip()
