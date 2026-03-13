# brighter-bookings-ms

Manages property bookings and status transitions.

**Port:** `8002` | **Prefix:** `/bookings`

## Endpoints

| Method | Path | Scope |
|---|---|---|
| `GET` | `/bookings/slots?property_id=` | Any auth — returns `[{start, end}]` |
| `GET` | `/bookings` | `bookings:read` / `bookings:manage` / admin |
| `POST` | `/bookings` | `bookings:write` |
| `GET` | `/bookings/{id}` | Same as list |
| `PATCH` | `/bookings/{id}/status` | Depends on transition |
| `DELETE` | `/bookings/{id}` | `admin:bookings:delete` |

## Status transitions

```
PENDING  → CONFIRMED  (property owner)   PENDING  → CANCELLED  (customer)
CONFIRMED → COMPLETED  (property owner)   CONFIRMED → CANCELLED  (customer)
CONFIRMED → NO_SHOW    (property owner)
```

## Running

```bash
uv run uvicorn main:application --host 0.0.0.0 --port 8002
uv run pytest
```

## Key env vars

| Variable | Default |
|---|---|
| `DB_URL` | `sqlite://:memory:` |
| `PROPERTIES_MS_URL` | `http://localhost:8001` |
| `PAYMENTS_MS_URL` | `http://localhost:8003` |
| `REDIS_URL` | `redis://redis:6379/0` |

## Notes

- Auth via Traefik headers — no JWT validation here.
- Calls `properties-ms` to fetch property owner at booking creation; `property_owner_id` is then denormalized on the booking.
- Calls `payments-ms` to issue a refund when a property owner cancels a confirmed booking.
- Redis caches `/bookings/slots` keyed by `slots:{property_id}`, TTL 60s.
- Tests mock CRUD with `AsyncMock`; use `customer_client`/`owner_client`/`admin_client` fixtures.
