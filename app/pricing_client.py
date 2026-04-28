"""Thin async client for the properties-ms pricing resolve endpoint."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

import httpx
from loguru import logger

from app import settings


class PricingClient:
    """Calls properties-ms /properties/{id}/pricing/resolve.

    Applies 2 s timeout and 1 retry. On any failure falls back to flat
    base_price × num_nights so booking creation always succeeds.
    """

    def __init__(self, base_url: str | None = None) -> None:
        self._base_url = base_url or settings.properties_ms_url

    async def resolve(
        self,
        property_id: UUID,
        start_date: date,
        end_date: date,
        base_price: Decimal,
    ) -> tuple[Decimal, Decimal]:
        """Return (total_price, avg_price_per_night) for the requested stay.

        Falls back to flat calculation when properties-ms is unreachable.
        """
        num_nights = (end_date - start_date).days
        flat_total = (base_price * Decimal(num_nights)).quantize(Decimal("0.01"))

        url = f"{self._base_url}/properties/{property_id}/pricing/resolve"
        params = {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()}

        for attempt in range(2):
            try:
                async with httpx.AsyncClient(timeout=2.0) as client:
                    resp = await client.get(url, params=params)
                    resp.raise_for_status()
                    data = resp.json()
                total = Decimal(str(data["total"])).quantize(Decimal("0.01"))
                avg = (total / Decimal(num_nights)).quantize(Decimal("0.01"))
                return total, avg
            except Exception as exc:
                if attempt == 0:
                    logger.warning("Pricing resolve attempt failed (will retry): {}", exc)
                else:
                    logger.warning(
                        "Pricing resolve failed after retry — falling back to flat rate: {}",
                        exc,
                    )

        return flat_total, base_price


def get_pricing_client() -> PricingClient:
    return PricingClient()
