"""SSRF-guard tests for external feed URLs (BTR-41)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.feed_url import (
    FeedUrlError,
    assert_host_is_public,
    is_allowed_feed_host,
    is_private_address,
    validate_feed_url,
)


class TestHostAllowlist:
    def test_booking_com_and_subdomains_allowed(self):
        assert is_allowed_feed_host("booking.com")
        assert is_allowed_feed_host("admin.booking.com")
        assert is_allowed_feed_host("ical.BOOKING.COM")  # case-insensitive

    def test_lookalike_hosts_rejected(self):
        assert not is_allowed_feed_host("booking.com.evil.com")
        assert not is_allowed_feed_host("notbooking.com")
        assert not is_allowed_feed_host("evil.com")


class TestValidateFeedUrl:
    def test_valid_https_booking_url(self):
        url = "https://admin.booking.com/hotel/ical.html?t=abc"
        assert validate_feed_url(url) == url

    def test_http_scheme_rejected(self):
        with pytest.raises(FeedUrlError):
            validate_feed_url("http://admin.booking.com/ical.html")

    def test_non_booking_host_rejected(self):
        with pytest.raises(FeedUrlError):
            validate_feed_url("https://evil.com/ical.html")


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
