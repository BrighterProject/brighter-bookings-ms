"""Thin async client for the properties-ms pricing resolve endpoint."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

import httpx
from fastapi import HTTPException, status
from loguru import logger

from app import settings


class PricingGapError(Exception):
    """Raised when the requested stay includes nights with no price set.

    Carries the ISO dates properties-ms reported as unpriced so the caller can
    surface them to the guest.
    """

    def __init__(self, unpriced_dates: list[str]) -> None:
        self.unpriced_dates = unpriced_dates
        super().__init__(f"Stay includes {len(unpriced_dates)} unpriced night(s)")


class PricingClient:
    """Calls properties-ms ``/properties/{id}/pricing/resolve``.

    2 s timeout, 1 retry on transient network failure. There is no base-price
    fallback — a stay that cannot be priced is rejected (fail closed):

    * 409 from properties-ms -> :class:`PricingGapError` (unpriced nights)
    * unreachable / other error -> ``HTTPException`` 502
    """

    def __init__(self, base_url: str | None = None) -> None:
        self._base_url = base_url or settings.properties_ms_url

    async def resolve(
        self,
        property_id: UUID,
        start_date: date,
        end_date: date,
    ) -> tuple[Decimal, Decimal]:
        """Return ``(total_price, avg_price_per_night)`` for the requested stay.

        Raises:
            PricingGapError: some nights in the range have no price set (409).
            HTTPException: properties-ms is unreachable or errored (502).
        """
        num_nights = (end_date - start_date).days
        url = f"{self._base_url}/properties/{property_id}/pricing/resolve"
        params = {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        }

        last_exc: Exception | None = None
        for attempt in range(2):
            try:
                async with httpx.AsyncClient(timeout=2.0) as client:
                    resp = await client.get(url, params=params)
            except httpx.RequestError as exc:
                last_exc = exc
                logger.warning(
                    "Pricing resolve attempt {} failed (transient): {}",
                    attempt + 1,
                    exc,
                )
                continue

            if resp.status_code == status.HTTP_409_CONFLICT:
                detail = resp.json().get("detail", {})
                raise PricingGapError(detail.get("unpriced_dates", []))
            if resp.status_code >= 400:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"properties-ms pricing resolve returned {resp.status_code}",
                )

            data = resp.json()
            total = Decimal(str(data["total"])).quantize(Decimal("0.01"))
            avg = (total / Decimal(num_nights)).quantize(Decimal("0.01"))
            return total, avg

        # Both attempts hit a transient network error — fail closed.
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="properties-ms pricing resolve unreachable",
        ) from last_exc


def get_pricing_client() -> PricingClient:
    return PricingClient()
