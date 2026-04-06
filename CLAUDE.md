# CLAUDE.md — brighter-bookings-ms

FastAPI microservice for managing property bookings (part of the BrighterProject platform).

## Package management

Always use `uv`. Never use `pip` directly.

```bash
uv add <package>       # add dependency
uv sync                # install from lockfile
uv run <command>       # run in the venv
```

## Running

```bash
uv run pytest                                                       # run tests
uv run uvicorn main:application --host 0.0.0.0 --port 8002         # dev server
```

## Architecture

### Technology Stack

- **API Framework**: FastAPI with Uvicorn
- **Database**: PostgreSQL with Tortoise ORM and Aerich migrations
- **Testing**: pytest with AsyncMock-based CRUD mocking (no real DB in tests)

## Auth architecture — critical

Auth is delegated entirely to Traefik via `forwardAuth`. JWT validation happens at the gateway. This service only reads the headers Traefik injects after a successful check:

| Header          | Type   | Description                        |
|-----------------|--------|------------------------------------|
| `X-User-Id`     | UUID   | Authenticated user's ID            |
| `X-Username`    | string | Authenticated user's username      |
| `X-User-Scopes` | string | Space-separated list of scopes     |

`get_current_user()` in `app/deps.py` reads these headers — it does not validate any token itself. **Do not add JWT validation middleware inside this service.**

## Cross-service calls

Bookings-ms calls properties-ms via `PropertiesClient` in `app/deps.py` using the internal Docker network (`http://properties-ms:8001`). It forwards the same Traefik headers so properties-ms auth works normally.

`PropertiesClient` is injected as a FastAPI dependency via `get_properties_client()`. Override this in tests to mock HTTP calls.

It also calls payments-ms via `PaymentsClient` in `app/deps.py` (`http://payments-ms:8003`) to issue refunds when a property owner cancels a confirmed booking (`refund_booking(booking_id)`).

## Project structure

```
app/
  settings.py          # DB_URL, USERS_MS_URL, PROPERTIES_MS_URL (env vars)
  models.py            # Tortoise ORM model: Booking + BookingStatus
  schemas.py           # Pydantic schemas: BookingCreate, BookingStatusUpdate, BookingResponse, BookingFilters, BookingSlot
  crud.py              # BookingCRUD — all DB operations (conflict checks, CRUD)
  deps.py              # Auth deps, PropertiesClient, scope checkers
  scopes.py            # BookingScope StrEnum + BOOKING_SCOPE_DESCRIPTIONS
  routers/
    booking.py         # /bookings CRUD + status transitions + GET /bookings/slots
tests/
  conftest.py          # Fixtures: customer_client, owner_client, admin_client, anon_app, client_factory
  factories.py         # make_customer(), make_property_owner(), make_admin(), booking_response(), etc.
  test_bookings.py     # Full endpoint test suite
  test_scopes.py       # Scope enum/description tests
```

## Scopes

| Scope                   | Who has it     | Purpose                                      |
|-------------------------|----------------|----------------------------------------------|
| `bookings:read`         | Customer       | View own bookings                            |
| `bookings:write`        | Customer       | Create a booking                             |
| `bookings:cancel`       | Customer       | Cancel own booking                           |
| `bookings:manage`       | Property owner    | Confirm / complete / no_show for own properties  |
| `admin:bookings`        | Admin          | Super-scope                                  |
| `admin:bookings:read`   | Admin          | Read any booking                             |
| `admin:bookings:write`  | Admin          | Modify any booking status                    |
| `admin:bookings:delete` | Admin          | Hard-delete any booking                      |

## Status transitions

```
PENDING  → CONFIRMED  (property owner / admin)
PENDING  → CANCELLED  (customer / admin)
CONFIRMED → COMPLETED  (property owner / admin)
CONFIRMED → CANCELLED  (customer / admin)
CONFIRMED → NO_SHOW    (property owner / admin)
```

Terminal states: `COMPLETED`, `CANCELLED`, `NO_SHOW` — no further transitions allowed.

## Anonymous slots endpoint

`GET /bookings/slots?property_id=<uuid>` — returns `[{start_datetime, end_datetime}]` for all PENDING+CONFIRMED bookings at a property. **No user identity exposed. Public — no auth required.** Rate limited to 60 requests/minute per IP via `slowapi` + Redis (`app/limiter.py`). Used by the frontend booking form to show occupied date ranges without revealing who booked them.

`BookingSlot` schema: only `start_datetime` + `end_datetime`. Define it **before** `/{booking_id}` routes in the router to avoid FastAPI matching "slots" as a UUID path param.

## Booking model

Fields: `id`, `property_id`, `property_owner_id`, `user_id`, `start_datetime`, `end_datetime`, `status`, `price_per_night`, `total_price`, `currency`, `notes`, `updated_at`.

`notes` stores JSON-encoded guest information (name, contact details, special requests) submitted at booking time. It is opaque to booking logic — treat it as a blob.

`property_owner_id` is denormalized from properties-ms at booking creation time to avoid cross-service lookups on every status update. Do not expose it as a writable field.

### Pricing model

Nightly pricing: `total_price = price_per_night × num_nights` where `num_nights = (end_date - start_date).days`. Minimum 1 night. `price_per_night` is copied from the property at creation time.

## Testing conventions

- **Mock the CRUD layer** with `AsyncMock` — no DB (router tests)
- **Mock PropertiesClient** via `client_factory(..., properties_client=mock_vc)` dependency override
- Status transition tests: use `booking_model(**overrides)` (Pydantic object) for `get_booking` mock, since the router accesses `.status`, `.user_id`, `.property_owner_id` attributes
- Use `anon_app` for real scope/auth dep checks (403/422 assertions) — also used for public endpoints like `/slots`
- Rate limiting is disabled in tests via `SLOWAPI_NO_LIMITS=true` set at the top of `conftest.py`

```python
# Router test pattern
with patch("app.routers.booking.booking_crud") as mock_crud:
    mock_crud.list_bookings = AsyncMock(return_value=[booking_response()])
    resp = customer_client.get("/bookings")
assert resp.status_code == 200
```

## Redis cache (`app/cache.py`)
- Caches `GET /bookings/slots` keyed by `slots:{property_id}`, TTL 60s
- Invalidated in `create_booking` and `update_booking_status` for the affected property
- All Redis ops silently degrade on failure

## Database

- Tests: SQLite in-memory (default, mocked via CRUD patch)
- Production: PostgreSQL (`DB_URL` env var)
- Migrations: Aerich

```bash
uv run aerich migrate --name <description>
uv run aerich upgrade
```

## Environment variables

| Variable        | Default                   | Description                        |
|-----------------|---------------------------|------------------------------------|
| `DB_URL`        | `sqlite://:memory:`       | Database connection string         |
| `USERS_MS_URL`  | `http://localhost:8000`   | Users microservice base URL        |
| `PROPERTIES_MS_URL` | `http://localhost:8001`   | Properties microservice base URL       |
| `PAYMENTS_MS_URL` | `http://localhost:8003` | Payments microservice base URL     |
| `REDIS_URL`       | `redis://localhost:6379/0` | Redis connection string (cache)  |
