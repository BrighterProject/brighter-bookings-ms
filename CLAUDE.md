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
uv run ruff check .                                                 # lint
uv run ty check                                                     # type check
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
  schemas.py           # Pydantic schemas: BookingCreate, BookingStatusUpdate, BookingResponse, BookingEnriched, BookingFilters, BookingSlot
  crud.py              # BookingCRUD — all DB operations (conflict checks, CRUD)
  deps.py              # Auth deps, PropertiesClient, scope checkers
  scopes.py            # BookingScope StrEnum + BOOKING_SCOPE_DESCRIPTIONS
  feed_url.py          # SSRF guards for external feed URLs (BTR-41)
  services/
    ical_parser.py     # parse Booking.com iCal exports → normalized events (BTR-41)
    calendar_sync.py   # fetch + diff + upsert sync engine (BTR-41)
  routers/
    booking.py         # /bookings CRUD + status transitions + GET /bookings/slots
    calendar_feeds.py  # owner-facing /bookings/calendar-feeds CRUD + sync-now (BTR-41)
    internal_calendar_sync.py  # /internal/calendar-sync/run cron sweep (BTR-41)
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

`GET /bookings/slots?property_id=<uuid>` — returns `[{start_date, end_date}]` for all PENDING+CONFIRMED bookings at a property. **No user identity exposed. Public — no auth required.** Rate limited to 60 requests/minute per IP via `slowapi` + Redis (`app/limiter.py`). Used by the frontend booking form to show occupied date ranges without revealing who booked them.

`BookingSlot` schema: only `start_date` + `end_date`. Define it **before** `/{booking_id}` routes in the router to avoid FastAPI matching "slots" as a UUID path param.

## Booking model

Fields: `id`, `property_id`, `property_owner_id`, `user_id`, `start_date`, `end_date`, `status`, `price_per_night`, `total_price`, `currency`, `guest_name`, `guest_email`, `guest_phone`, `special_requests`, `channel`, `external_uid`, `updated_at`.

`property_owner_id` is denormalized from properties-ms at booking creation time to avoid cross-service lookups on every status update. Do not expose it as a writable field.

`channel` (`platform` default / `booking_com`) tags where a booking originated; `external_uid` is the source iCal `VEVENT` UID (null for platform bookings). Unique together on `(property_id, channel, external_uid)` for idempotent channel upserts. See **Channel calendar import** below.

### Pricing model

Nightly pricing: `total_price = price_per_night × num_nights` where `num_nights = (end_date - start_date).days`. Minimum 1 night. `price_per_night` is copied from the property at creation time.

## Channel calendar import (BTR-41)

Import-only iCal sync so a property is never sold twice for the same night. We
**import** Booking.com reservations to protect our calendar; we never publish a feed
back or push availability (owner manages Booking.com manually). See the design spec
`docs/superpowers/specs/2026-07-12-bookingcom-calendar-import-design.md`.

- `ExternalCalendarFeed` model: owner links a property to a Booking.com iCal export
  URL. A k8s CronJob (`/internal/calendar-sync/run`, every ~10 min, `concurrencyPolicy:
  Forbid`) sweeps active feeds.
- Each reservation becomes a **real, read-only `Booking` row** (`channel=booking_com`,
  `status=CONFIRMED`, `user_id=CHANNEL_GUEST_USER_ID` sentinel, price `0`,
  `guest_name="Booking.com"`). This reuses the existing conflict check + `/slots`
  picker with zero new wiring — imports block platform bookings automatically.
- **Read-only enforcement**: the status-transition endpoint rejects (409) any
  transition on a `channel != platform` booking — the sync engine owns their
  lifecycle. Truncation/cancellation are direct field writes by the engine and bypass
  those API rules by design.
- **Fail-safe sync** (`app/services/calendar_sync.py`): a fetch/parse error keeps all
  existing imported rows (never free a date we can't re-verify). Feeds are skipped when
  the **normalized** content hash (sorted `(uid,start,end)`, not the raw body) is
  unchanged. Vanished UIDs resolve by `end_date`: future → cancel; mid-stay → truncate
  `end_date=today`; fully elapsed → leave untouched ("the vanishing past").
- **SSRF guard** (`app/feed_url.py`): feed URLs must be `https://*.booking.com`;
  redirects are followed but re-validated per hop against the host allowlist + a
  private/link-local/loopback IP denylist.
- Metrics: `calendar_feeds_synced_total`, `channel_bookings_imported_total`,
  `calendar_feed_fetch_errors_total`, `channel_overbookings_total`.
- Owner API (scope `bookings:manage` + property ownership): `GET/POST
  /bookings/calendar-feeds`, `DELETE /bookings/calendar-feeds/{id}`, `POST
  /bookings/calendar-feeds/{id}/sync-now`. Managed in the admin panel property form
  ("Външни календари" section).

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
- Migrations: native tortoise CLI — config in `pyproject.toml` (`[tool.tortoise]`), stored in `./migrations/models/`

```bash
uv run tortoise -c main.TORTOISE_ORM makemigrations
uv run tortoise -c main.TORTOISE_ORM migrate
```

## Environment variables

| Variable        | Default                   | Description                        |
|-----------------|---------------------------|------------------------------------|
| `DB_URL`        | `sqlite://:memory:`       | Database connection string         |
| `USERS_MS_URL`  | `http://localhost:8000`   | Users microservice base URL        |
| `PROPERTIES_MS_URL` | `http://localhost:8001`   | Properties microservice base URL       |
| `PAYMENTS_MS_URL` | `http://localhost:8003` | Payments microservice base URL     |
| `REDIS_URL`       | `redis://localhost:6379/0` | Redis connection string (cache)  |
| `SLOWAPI_NO_LIMITS` | unset | Set `true` in tests to disable rate limiting on `/slots` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://otel-collector:4317` | OTLP gRPC endpoint |
| `OTEL_SDK_DISABLED` | `false` | Set `true` to skip telemetry (CI / light dev) |
| `LOG_COLORIZE` | `false` | Set `true` for ANSI-coloured logs in compose |
| `INTERNAL_CRON_SECRET` | `""` | Shared secret gating `/internal/*` cron endpoints (calendar sweep) |
| `CALENDAR_SYNC_FETCH_TIMEOUT` | `10` | Per-feed iCal fetch timeout (s) — channel import (BTR-41) |
| `CALENDAR_SYNC_JITTER_MS` | `500` | Max random delay between feeds in a sweep (BTR-41) |

## Git & Branch Workflow

- **Branch off `dev`**: all new work starts from `dev` — use `feat/<slug>` (or `fix/`, `chore/`, `test/`, `refactor/` as appropriate)
- **PR targets `dev`**: never push directly to `dev` or `main`
- **Approval required**: at least one human approval before merging
- **CI must be green**: all checks must pass before merging
- **Staging on green `dev`**: a passing `dev` triggers an automatic staging deployment
- **`dev` → `main` is manual**: when `dev` is stable and ready to ship, open a PR from `dev` to `main` and merge manually
- **Hotfixes bypass `dev`**: branch off `main` as `fix/<slug>`, PR directly to `main`, then backport to `dev`
- **Branch cleanup**: delete merged branches periodically — keep them for a while for reference, then clean up
