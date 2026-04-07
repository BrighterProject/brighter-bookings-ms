"""
Integration tests for Redis caching in bookings-ms.

These tests require a live Redis instance reachable at REDIS_URL
(default: redis://localhost:6379/0).

Run with:
    pytest -m integration
"""

from uuid import uuid4

import pytest

from app.cache import get_slots_cache, invalidate_slots_cache, set_slots_cache

_SLOT = {"start_datetime": "2026-06-01T14:00:00", "end_datetime": "2026-06-03T11:00:00"}


@pytest.mark.integration
class TestSlotsCache:
    async def test_get_returns_none_for_missing_key(self):
        assert await get_slots_cache(uuid4()) is None

    async def test_set_then_get_returns_cached_data(self):
        property_id = uuid4()
        await set_slots_cache(property_id, [_SLOT])
        result = await get_slots_cache(property_id)
        assert result == [_SLOT]

    async def test_invalidate_removes_cached_data(self):
        property_id = uuid4()
        await set_slots_cache(property_id, [_SLOT])
        await invalidate_slots_cache(property_id)
        assert await get_slots_cache(property_id) is None

    async def test_set_overwrites_existing_entry(self):
        property_id = uuid4()
        slot_a = {"start_datetime": "2026-06-01T14:00:00", "end_datetime": "2026-06-02T11:00:00"}
        slot_b = {"start_datetime": "2026-07-01T14:00:00", "end_datetime": "2026-07-03T11:00:00"}
        await set_slots_cache(property_id, [slot_a])
        await set_slots_cache(property_id, [slot_b])
        result = await get_slots_cache(property_id)
        assert result == [slot_b]
