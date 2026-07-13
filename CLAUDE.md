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

`GET /bookings/slots?property_id=<uuid>` — returns `[{start_date, end_date}]` for all PENDING+CONFIRMED bookings at a property. **No user identity exposed. Public — no auth required.** Rate limited to 60 requests/minute per IP via `slowapi` + Redis (`app/limiter.py`). Used by the frontend booking form to show occupied date ranges without revealing who booked them.

`BookingSlot` schema: only `start_date` + `end_date`. Define it **before** `/{booking_id}` routes in the router to avoid FastAPI matching "slots" as a UUID path param.

## Booking model

Fields: `id`, `property_id`, `property_owner_id`, `user_id`, `start_date`, `end_date`, `status`, `price_per_night`, `total_price`, `currency`, `num_guests`, `guest_name`, `guest_email`, `guest_phone`, `guest_country`, `special_requests`, `gap_adjustment_pct`, `payment_method`, `checkin_link_sent_at`, `guest_data_purged_at`, `updated_at`.

`property_owner_id` is denormalized from properties-ms at booking creation time to avoid cross-service lookups on every status update. Do not expose it as a writable field.

### Pricing model — resolved from properties-ms, fail-closed

`app/pricing_client.py::PricingClient` calls properties-ms `GET /properties/{id}/pricing/resolve` during booking creation (`app/routers/booking.py`) — there is no owner-set `price_per_night` input and no base-price fallback:

- 2s timeout, 1 retry on transient network error; unreachable/error → 502.
- Any night in the stay with no configured price → properties-ms returns 409 → `PricingClient.resolve` raises `PricingGapError` → booking creation returns 409 with `unpriced_dates`.
- **Gap-tax filler**: if the stay is shorter than the property's `min_nights` and the property has `enable_gap_filler` + a nonzero `gap_tax_pct`, both `total_price` and `price_per_night` are multiplied by `1 + gap_tax_pct/100` and the applied percentage is stored on `gap_adjustment_pct`.
- `price_per_night` stored on the booking is the resolved **average** nightly rate for the stay, not a flat per-night price.

Nightly pricing: `total_price = avg_price_per_night × num_nights` where `num_nights = (end_date - start_date).days` (min 1 night), before/after gap-tax adjustment.

## Self check-in & guest identities (BTR-15)

Guests fill in ID/passport details before arrival via a signed, tokenized link — feeds Bulgaria's ESTI tourist-registration reporting.

- `GuestIdentity` model (`app/models.py`): `booking` FK, `first_name`/`middle_name`/`last_name` (survive purge), plus `date_of_birth`, `gender`, `citizenship`, `document_type`, `document_number` (`EncryptedCharField`), `document_issuing_country`, `pin_egn` (`EncryptedCharField`, BG nationals only) — all nullable at the DB level so the purge job can null them out after the ESTI reporting window while keeping names.
- `app/checkin_token.py` — signs/verifies a JWT (`CHECKIN_TOKEN_SECRET`, HS256) binding a booking id with an expiry of `end_date + CHECKIN_TOKEN_GRACE_DAYS`.
- `app/routers/checkin.py` (public, token-authed) — `GET /checkin/{token}` returns the guest roster (`num_guests` slots); `POST /checkin/{token}/guests` fills the next open slot.
- `app/routers/guest_identities.py` (`/bookings/{id}/guests`) — admin/owner-facing CRUD, gated by `can_admin_write_guest_identity` / `can_view_guest_identities`.
- `app/routers/internal_checkin.py` (`/internal/checkin/*`, gated by `verify_internal_cron_secret` / `INTERNAL_CRON_SECRET`) — daily cron endpoints: `/dispatch` sends check-in links for bookings starting within `CHECKIN_DISPATCH_LEAD_DAYS`, a purge endpoint nulls all `_PURGE_FIELDS` after the reporting window.
- `app/checkin_dispatch.py` — `send_checkin_link` claims the booking atomically (`UPDATE ... WHERE checkin_link_sent_at IS NULL`) before emailing, so the immediate post-confirm dispatch (`maybe_send_checkin_link`, fired via `asyncio.create_task` on the `CONFIRMED` transition, not awaited by the request handler) can't double-send with the daily cron sweep. All dispatch/purge date math anchors to `Europe/Sofia` (`today_in_sofia()`), not UTC, since booking dates are bare dates and the CronJob pod runs in UTC.
- Tests: `test_checkin_token.py`, `test_checkin_dispatch.py`, `test_checkin_router.py`, `test_checkin_link_endpoint.py`, `test_internal_checkin.py`, `test_checkin_deps.py`.

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
| `CHECKIN_TOKEN_SECRET` | `""` | HS256 secret signing guest check-in links; required for `/checkin/*` |
| `CHECKIN_TOKEN_GRACE_DAYS` | `1` | Days past a booking's `end_date` a check-in token stays valid |
| `INTERNAL_CRON_SECRET` | `""` | Shared secret gating `/internal/checkin/*` cron endpoints |
| `CHECKIN_DISPATCH_LEAD_DAYS` | see `settings.py` | How far ahead of `start_date` the daily dispatch sweep sends links |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://otel-collector:4317` | OTLP gRPC endpoint |
| `OTEL_SDK_DISABLED` | `false` | Set `true` to skip telemetry (CI / light dev) |
| `LOG_COLORIZE` | `false` | Set `true` for ANSI-coloured logs in compose |

## Git & Branch Workflow

- **Branch off `dev`**: all new work starts from `dev` — use `feat/<slug>` (or `fix/`, `chore/`, `test/`, `refactor/` as appropriate)
- **PR targets `dev`**: never push directly to `dev` or `main`
- **Approval required**: at least one human approval before merging
- **CI must be green**: all checks must pass before merging
- **Staging on green `dev`**: a passing `dev` triggers an automatic staging deployment
- **`dev` → `main` is manual**: when `dev` is stable and ready to ship, open a PR from `dev` to `main` and merge manually
- **Hotfixes bypass `dev`**: branch off `main` as `fix/<slug>`, PR directly to `main`, then backport to `dev`
- **Branch cleanup**: delete merged branches periodically — keep them for a while for reference, then clean up
