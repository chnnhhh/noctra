"""Proxy helpers for scraper HTTP clients."""

import os
from urllib.parse import urlparse
from urllib.request import proxy_bypass_environment


def normalize_proxy_url(value: str | None) -> str | None:
    """Normalize proxy env values.

    Accepts either a full proxy URL (``http://host:port``) or a bare
    ``host:port`` value and always returns a usable URL for HTTP clients.
    """
    if not value:
        return None

    normalized = value.strip()
    if not normalized:
        return None

    if "://" not in normalized:
        normalized = f"http://{normalized}"

    return normalized


def get_proxy_for_url(url: str) -> str | None:
    """Return the effective proxy URL for *url* based on environment variables."""
    parsed = urlparse(url)
    scheme = (parsed.scheme or "").lower()
    hostname = parsed.hostname

    if hostname and proxy_bypass_environment(hostname):
        return None

    candidates: list[str]
    if scheme == "https":
        candidates = [
            "HTTPS_PROXY",
            "https_proxy",
            "ALL_PROXY",
            "all_proxy",
            "HTTP_PROXY",
            "http_proxy",
        ]
    elif scheme == "http":
        candidates = [
            "HTTP_PROXY",
            "http_proxy",
            "ALL_PROXY",
            "all_proxy",
        ]
    else:
        candidates = [
            "ALL_PROXY",
            "all_proxy",
        ]

    for name in candidates:
        value = normalize_proxy_url(os.getenv(name))
        if value:
            return value

    return None
