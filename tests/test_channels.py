"""Channel registry tests (BTR-41): display labels + host allowlist coverage."""

from __future__ import annotations

from app.channels import CHANNEL_SPECS, channel_display_name, is_allowed_feed_host
from app.models import BookingChannel


class TestChannelSpecs:
    def test_every_non_platform_channel_is_registered(self):
        # A new BookingChannel without a spec would silently reject all its feeds.
        for channel in BookingChannel:
            if channel is BookingChannel.PLATFORM:
                assert channel not in CHANNEL_SPECS
            else:
                assert channel in CHANNEL_SPECS

    def test_display_names(self):
        assert channel_display_name(BookingChannel.BOOKING_COM) == "Booking.com"
        assert channel_display_name(BookingChannel.AIRBNB) == "Airbnb"

    def test_display_name_falls_back_to_value(self):
        # PLATFORM has no spec — never used for imports, but must not raise.
        assert channel_display_name(BookingChannel.PLATFORM) == "platform"


class TestHostMatching:
    def test_exact_and_subdomain(self):
        assert is_allowed_feed_host("airbnb.com", BookingChannel.AIRBNB)
        assert is_allowed_feed_host("www.airbnb.com", BookingChannel.AIRBNB)

    def test_trailing_dot_and_case(self):
        assert is_allowed_feed_host("ADMIN.BOOKING.COM.", BookingChannel.BOOKING_COM)
