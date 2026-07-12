"""SSRF guards for external calendar feed URLs (BTR-41).

Two layers:

1. :func:`validate_feed_url` — cheap, synchronous scheme + per-channel host
   allowlist. Applied when an owner registers a feed and re-applied to every
   redirect hop. The host allowlist itself lives in :mod:`app.channels` so a new
   channel needs no edit here.
2. :func:`assert_host_is_public` — resolves the host and rejects any private /
   loopback / link-local address, so an allowlisted host can never be pointed at
   an internal service. Blocking (DNS); call it via ``asyncio.to_thread`` from
   async code.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

from app.channels import is_allowed_feed_host
from app.models import BookingChannel


class FeedUrlError(ValueError):
    """Raised when a feed URL fails an SSRF check."""


def validate_feed_url(url: str, channel: BookingChannel) -> str:
    """Return ``url`` unchanged if it is an ``https`` URL on ``channel``'s domain.

    Raises:
        FeedUrlError: if the scheme is not https or the host is not allowlisted
            for the given channel.
    """
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise FeedUrlError("Feed URL must use https")
    host = parsed.hostname or ""
    if not is_allowed_feed_host(host, channel):
        raise FeedUrlError(f"Feed URL host is not allowed for channel '{channel.value}'")
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
