"""Internal cron endpoint driving the external calendar sweep (BTR-41).

Gated by ``INTERNAL_CRON_SECRET`` and never exposed through Traefik. Driven by a
k8s CronJob every ~10 min with ``concurrencyPolicy: Forbid`` so a slow sweep can
never overlap the next fire and exhaust the DB pool.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.deps import verify_internal_cron_secret
from app.services.calendar_sync import sync_all_active_feeds

router = APIRouter(
    prefix="/internal/calendar-sync",
    tags=["internal"],
    dependencies=[Depends(verify_internal_cron_secret)],
)


@router.post("/run")
async def run_calendar_sync(request: Request) -> dict[str, int]:
    """Sweep all active feeds. Returns per-status counts."""
    return await sync_all_active_feeds()
