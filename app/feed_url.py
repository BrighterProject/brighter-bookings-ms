"""SSRF guards for external calendar feed URLs (BTR-41).

Two layers:

1. :func:`validate_feed_url` — cheap, synchronous scheme + host allowlist. Applied
   when an owner registers a feed and re-applied to every redirect hop.
2. :func:`assert_host_is_public` — resolves the host and rejects any private /
   loopback / link-local address, so an allowlisted host can never be pointed at
   an internal service. Blocking (DNS); call it via ``asyncio.to_thread`` from
   async code.
"""

from __future__ import annotations

import ipaddress
import socket
from typing import Final
from urllib.parse import urlparse

# v1 allowlist: only Booking.com. Widen deliberately when more channels ship.
_ALLOWED_HOST_EXACT: Final[frozenset[str]] = frozenset({"booking.com"})
_ALLOWED_HOST_SUFFIX: Final[str] = ".booking.com"


class FeedUrlError(ValueError):
    """Raised when a feed URL fails an SSRF check."""


def is_allowed_feed_host(host: str) -> bool:
    """True if ``host`` is booking.com or a subdomain of it (case-insensitive)."""
    host = host.lower().rstrip(".")
    return host in _ALLOWED_HOST_EXACT or host.endswith(_ALLOWED_HOST_SUFFIX)


def validate_feed_url(url: str) -> str:
    """Return ``url`` unchanged if it is an ``https://*.booking.com`` URL.

    Raises:
        FeedUrlError: if the scheme is not https or the host is not allowlisted.
    """
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise FeedUrlError("Feed URL must use https")
    host = parsed.hostname or ""
    if not is_allowed_feed_host(host):
        raise FeedUrlError("Feed URL host must be a booking.com domain")
    return url


def is_private_address(ip: str) -> bool:
    """True if ``ip`` is any non-globally-routable address (SSRF sinkhole)."""
    addr = ipaddress.ip_address(ip)
    return (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
    )


def assert_host_is_public(host: str) -> None:
    """Resolve ``host`` and raise if any address is private/link-local/loopback.

    Raises:
        FeedUrlError: if resolution fails or any resolved address is non-public.
    """
    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise FeedUrlError(f"Could not resolve feed host {host}") from exc
    for info in infos:
        ip = str(info[4][0])
        if is_private_address(ip):
            raise FeedUrlError(f"Feed host {host} resolves to a private address")
