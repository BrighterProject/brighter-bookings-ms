"""Per-channel configuration for external calendar import (BTR-41).

The parser (:mod:`app.services.ical_parser`) and the sync engine
(:mod:`app.services.calendar_sync`) are entirely channel-agnostic — every
channel exports the same all-day ``VALUE=DATE`` VEVENT shape. The only things
that differ per channel are the **host allowlist** (SSRF guard) and the
**display label** stamped on imported rows. Both live here.

Adding a new channel is a two-line change:

1. add a member to :class:`~app.models.BookingChannel`;
2. add its :class:`ChannelSpec` entry below.

No parser, sync-engine, or CRUD edits are required.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from app.models import BookingChannel


@dataclass(frozen=True)
class ChannelSpec:
    """Everything the platform needs to import one channel's iCal feed."""

    display_name: str  # stamped as ``guest_name`` on imported bookings
    allowed_hosts: tuple[str, ...]  # registrable domains; subdomains are allowed


CHANNEL_SPECS: Final[dict[BookingChannel, ChannelSpec]] = {
    BookingChannel.BOOKING_COM: ChannelSpec("Booking.com", ("booking.com",)),
    BookingChannel.AIRBNB: ChannelSpec("Airbnb", ("airbnb.com",)),
}
"""Channels that expose an importable iCal feed. ``PLATFORM`` is intentionally
absent — Brighter's own bookings never come from a feed."""


def channel_display_name(channel: BookingChannel) -> str:
    """Human label for a channel (fallback to the enum value for safety)."""
    spec = CHANNEL_SPECS.get(channel)
    return spec.display_name if spec is not None else channel.value


def is_allowed_feed_host(host: str, channel: BookingChannel) -> bool:
    """True if ``host`` belongs to ``channel``'s registrable domain(s).

    Matches the domain exactly or any subdomain of it, case-insensitively, so
    ``booking.com`` and ``admin.booking.com`` both pass for ``BOOKING_COM`` while
    ``booking.com.evil.com`` does not.
    """
    host = host.lower().rstrip(".")
    spec = CHANNEL_SPECS.get(channel)
    if spec is None:
        return False
    return any(host == domain or host.endswith("." + domain) for domain in spec.allowed_hosts)
