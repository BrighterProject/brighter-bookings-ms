"""Internal cron endpoint tests for the calendar sweep (BTR-41)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.deps import verify_internal_cron_secret
from app.routers.internal_calendar_sync import router

RUN = "/internal/calendar-sync/run"


def _authed_client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[verify_internal_cron_secret] = lambda: None
    return TestClient(app, raise_server_exceptions=True)


def test_run_sweeps_active_feeds():
    client = _authed_client()
    with patch(
        "app.routers.internal_calendar_sync.sync_all_active_feeds",
        new=AsyncMock(return_value={"total": 2, "ok": 2}),
    ) as sweep:
        resp = client.post(RUN)
    assert resp.status_code == 200
    assert resp.json() == {"total": 2, "ok": 2}
    sweep.assert_awaited_once()


def test_run_requires_cron_secret():
    # No dependency override + empty INTERNAL_CRON_SECRET in tests → always 401.
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app, raise_server_exceptions=True)
    resp = client.post(RUN, headers={"Authorization": "Bearer wrong"})
    assert resp.status_code == 401
