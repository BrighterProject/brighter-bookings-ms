"""Feed-management endpoint tests (BTR-41): ownership, SSRF, CRUD, sync-now."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.deps import get_current_user, get_properties_client
from app.limiter import limiter
from app.routers.calendar_feeds import router
from app.schemas import CalendarFeedResponse

from .factories import (
    PROPERTY_ID,
    make_admin,
    make_customer,
    make_property_owner,
    property_dict,
)

FEED_CRUD = "app.routers.calendar_feeds.calendar_feed_crud"


def _build_app(user, properties_client) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.state.limiter = limiter
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_properties_client] = lambda: properties_client
    return TestClient(app, raise_server_exceptions=True)


def _props_client(owner_id):
    mock = MagicMock()
    mock.get_property = AsyncMock(return_value=property_dict(owner_id=str(owner_id)))
    return mock


def _feed_resp(**ov) -> CalendarFeedResponse:
    base = dict(
        id=uuid4(),
        property_id=PROPERTY_ID,
        channel="booking_com",
        url="https://admin.booking.com/ical.html?t=x",
        is_active=True,
        last_synced_at=None,
        last_status=None,
        last_error=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    return CalendarFeedResponse(**{**base, **ov})


class TestListFeeds:
    def test_owner_lists_own_property_feeds(self):
        owner = make_property_owner()
        client = _build_app(owner, _props_client(owner.id))
        with patch(FEED_CRUD) as crud:
            crud.list_for_property = AsyncMock(return_value=[_feed_resp()])
            resp = client.get(f"/bookings/calendar-feeds?property_id={PROPERTY_ID}")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_non_owner_gets_403(self):
        owner = make_property_owner()
        # Property owned by someone else.
        client = _build_app(owner, _props_client(uuid4()))
        with patch(FEED_CRUD) as crud:
            crud.list_for_property = AsyncMock(return_value=[])
            resp = client.get(f"/bookings/calendar-feeds?property_id={PROPERTY_ID}")
        assert resp.status_code == 403

    def test_customer_without_manage_gets_403(self):
        customer = make_customer()
        client = _build_app(customer, _props_client(customer.id))
        resp = client.get(f"/bookings/calendar-feeds?property_id={PROPERTY_ID}")
        assert resp.status_code == 403

    def test_admin_bypasses_ownership(self):
        client = _build_app(make_admin(), _props_client(uuid4()))
        with patch(FEED_CRUD) as crud:
            crud.list_for_property = AsyncMock(return_value=[])
            resp = client.get(f"/bookings/calendar-feeds?property_id={PROPERTY_ID}")
        assert resp.status_code == 200


class TestCreateFeed:
    def test_owner_creates_feed(self):
        owner = make_property_owner()
        client = _build_app(owner, _props_client(owner.id))
        with patch(FEED_CRUD) as crud:
            crud.create = AsyncMock(return_value=_feed_resp())
            resp = client.post(
                "/bookings/calendar-feeds",
                json={"property_id": str(PROPERTY_ID), "url": "https://admin.booking.com/i.ics"},
            )
        assert resp.status_code == 201

    @pytest.mark.parametrize(
        "url",
        ["http://admin.booking.com/i.ics", "https://evil.com/i.ics", "ftp://booking.com/i.ics"],
    )
    def test_ssrf_rejected_at_schema(self, url: str):
        owner = make_property_owner()
        client = _build_app(owner, _props_client(owner.id))
        resp = client.post(
            "/bookings/calendar-feeds",
            json={"property_id": str(PROPERTY_ID), "url": url},
        )
        assert resp.status_code == 422

    def test_non_owner_create_403(self):
        owner = make_property_owner()
        client = _build_app(owner, _props_client(uuid4()))
        resp = client.post(
            "/bookings/calendar-feeds",
            json={"property_id": str(PROPERTY_ID), "url": "https://admin.booking.com/i.ics"},
        )
        assert resp.status_code == 403


class TestDeleteFeed:
    def test_owner_deletes(self):
        owner = make_property_owner()
        client = _build_app(owner, _props_client(owner.id))
        with patch(FEED_CRUD) as crud:
            crud.get = AsyncMock(return_value=_feed_resp())
            crud.delete = AsyncMock(return_value=True)
            resp = client.delete(f"/bookings/calendar-feeds/{uuid4()}")
        assert resp.status_code == 204

    def test_missing_feed_404(self):
        owner = make_property_owner()
        client = _build_app(owner, _props_client(owner.id))
        with patch(FEED_CRUD) as crud:
            crud.get = AsyncMock(return_value=None)
            resp = client.delete(f"/bookings/calendar-feeds/{uuid4()}")
        assert resp.status_code == 404

    def test_non_owner_delete_403(self):
        owner = make_property_owner()
        client = _build_app(owner, _props_client(uuid4()))
        with patch(FEED_CRUD) as crud:
            crud.get = AsyncMock(return_value=_feed_resp())
            resp = client.delete(f"/bookings/calendar-feeds/{uuid4()}")
        assert resp.status_code == 403


class TestSyncNow:
    def test_owner_triggers_sync(self):
        owner = make_property_owner()
        client = _build_app(owner, _props_client(owner.id))
        feed = _feed_resp()
        with (
            patch(FEED_CRUD) as crud,
            patch("app.routers.calendar_feeds.sync_feed", new=AsyncMock()) as sync,
        ):
            crud.get = AsyncMock(return_value=feed)
            resp = client.post(f"/bookings/calendar-feeds/{feed.id}/sync-now")
        assert resp.status_code == 200
        sync.assert_awaited_once()
