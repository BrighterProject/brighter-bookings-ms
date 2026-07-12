"""SSRF-guard tests for external feed URLs (BTR-41)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.channels import is_allowed_feed_host
from app.feed_url import (
    FeedUrlError,
    assert_host_is_public,
    is_private_address,
    validate_feed_url,
)
from app.models import BookingChannel

BC = BookingChannel.BOOKING_COM
AB = BookingChannel.AIRBNB


class TestHostAllowlist:
    def test_booking_com_and_subdomains_allowed(self):
        assert is_allowed_feed_host("booking.com", BC)
        assert is_allowed_feed_host("admin.booking.com", BC)
        assert is_allowed_feed_host("ical.BOOKING.COM", BC)  # case-insensitive

    def test_airbnb_and_subdomains_allowed(self):
        assert is_allowed_feed_host("airbnb.com", AB)
        assert is_allowed_feed_host("www.airbnb.com", AB)

    def test_lookalike_hosts_rejected(self):
        assert not is_allowed_feed_host("booking.com.evil.com", BC)
        assert not is_allowed_feed_host("notbooking.com", BC)
        assert not is_allowed_feed_host("evil.com", BC)

    def test_channel_hosts_do_not_cross(self):
        # An Airbnb URL must not validate as a Booking.com feed and vice-versa.
        assert not is_allowed_feed_host("www.airbnb.com", BC)
        assert not is_allowed_feed_host("admin.booking.com", AB)

    def test_platform_channel_has_no_feed_host(self):
        assert not is_allowed_feed_host("booking.com", BookingChannel.PLATFORM)


class TestValidateFeedUrl:
    def test_valid_https_booking_url(self):
        url = "https://admin.booking.com/hotel/ical.html?t=abc"
        assert validate_feed_url(url, BC) == url

    def test_valid_https_airbnb_url(self):
        url = "https://www.airbnb.com/calendar/ical/12345.ics?s=token"
        assert validate_feed_url(url, AB) == url

    def test_http_scheme_rejected(self):
        with pytest.raises(FeedUrlError):
            validate_feed_url("http://admin.booking.com/ical.html", BC)

    def test_non_booking_host_rejected(self):
        with pytest.raises(FeedUrlError):
            validate_feed_url("https://evil.com/ical.html", BC)

    def test_airbnb_url_rejected_for_booking_channel(self):
        with pytest.raises(FeedUrlError):
            validate_feed_url("https://www.airbnb.com/calendar/ical/1.ics", BC)


class TestPrivateAddress:
    @pytest.mark.parametrize(
        "ip",
        ["127.0.0.1", "10.0.0.5", "172.16.3.4", "192.168.1.1", "169.254.1.1", "::1", "0.0.0.0"],
    )
    def test_private_addresses_flagged(self, ip: str):
        assert is_private_address(ip)

    @pytest.mark.parametrize("ip", ["8.8.8.8", "1.1.1.1"])
    def test_public_addresses_pass(self, ip: str):
        assert not is_private_address(ip)


class TestAssertHostIsPublic:
    def test_public_host_ok(self):
        with patch("app.feed_url.socket.getaddrinfo") as gai:
            gai.return_value = [(2, 1, 6, "", ("93.184.216.34", 443))]
            assert_host_is_public("admin.booking.com")  # no raise

    def test_private_resolution_rejected(self):
        # An allowlisted host that (mis)resolves to a private IP is blocked.
        with patch("app.feed_url.socket.getaddrinfo") as gai:
            gai.return_value = [(2, 1, 6, "", ("127.0.0.1", 443))]
            with pytest.raises(FeedUrlError):
                assert_host_is_public("admin.booking.com")

    def test_unresolvable_host_rejected(self):
        import socket as _socket

        with (
            patch("app.feed_url.socket.getaddrinfo", side_effect=_socket.gaierror),
            pytest.raises(FeedUrlError),
        ):
            assert_host_is_public("nope.booking.com")
