"""Channel registry tests (BTR-41): display labels + host allowlist coverage."""

from __future__ import annotations

import importlib

from app.channels import CHANNEL_SPECS, channel_display_name, is_allowed_feed_host
from app.models import BookingChannel

# Import channels that must always be registered (production defaults). ``DEV``
# is intentionally excluded — it is opt-in behind ENABLE_DEV_CALENDAR_CHANNEL.
_ALWAYS_ON = {BookingChannel.BOOKING_COM, BookingChannel.AIRBNB}


class TestChannelSpecs:
    def test_every_non_platform_channel_is_registered(self):
        # A production channel without a spec would silently reject all its feeds.
        for channel in _ALWAYS_ON:
            assert channel in CHANNEL_SPECS
        # PLATFORM never imports; DEV is gated off by default (see gate test).
        assert BookingChannel.PLATFORM not in CHANNEL_SPECS
        assert BookingChannel.DEV not in CHANNEL_SPECS

    def test_display_names(self):
        assert channel_display_name(BookingChannel.BOOKING_COM) == "Booking.com"
        assert channel_display_name(BookingChannel.AIRBNB) == "Airbnb"

    def test_display_name_falls_back_to_value(self):
        # PLATFORM has no spec — never used for imports, but must not raise.
        assert channel_display_name(BookingChannel.PLATFORM) == "platform"


class TestDevChannelGate:
    def _reload_channels(self):
        import app.channels
        import app.settings

        importlib.reload(app.settings)
        return importlib.reload(app.channels)

    def test_dev_channel_absent_by_default(self, monkeypatch):
        monkeypatch.delenv("ENABLE_DEV_CALENDAR_CHANNEL", raising=False)
        channels = self._reload_channels()
        assert BookingChannel.DEV not in channels.CHANNEL_SPECS
        assert not channels.is_allowed_feed_host("demo.ngrok-free.dev", BookingChannel.DEV)

    def test_dev_channel_registered_when_enabled(self, monkeypatch):
        monkeypatch.setenv("ENABLE_DEV_CALENDAR_CHANNEL", "true")
        channels = self._reload_channels()
        try:
            assert BookingChannel.DEV in channels.CHANNEL_SPECS
            assert channels.is_allowed_feed_host("demo.ngrok-free.dev", BookingChannel.DEV)
        finally:
            # Restore the default (disabled) module state for later tests.
            monkeypatch.delenv("ENABLE_DEV_CALENDAR_CHANNEL", raising=False)
            self._reload_channels()


class TestHostMatching:
    def test_exact_and_subdomain(self):
        assert is_allowed_feed_host("airbnb.com", BookingChannel.AIRBNB)
        assert is_allowed_feed_host("www.airbnb.com", BookingChannel.AIRBNB)

    def test_trailing_dot_and_case(self):
        assert is_allowed_feed_host("ADMIN.BOOKING.COM.", BookingChannel.BOOKING_COM)
