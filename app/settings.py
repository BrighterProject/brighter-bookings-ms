import os

db_url = os.environ.get("DB_URL", "sqlite://:memory:")
users_ms_url = os.environ.get("USERS_MS_URL", "http://localhost:8000")
properties_ms_url = os.environ.get("PROPERTIES_MS_URL", "http://localhost:8001")
payments_ms_url = os.environ.get("PAYMENTS_MS_URL", "http://localhost:8003")
notifications_ms_url = os.environ.get("NOTIFICATIONS_MS_URL", "http://localhost:8004")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

# Fernet key (base64) for encrypting GuestIdentity.document_number / pin_egn at rest.
# Generate with:
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
booking_field_encryption_key = os.environ.get("BOOKING_FIELD_ENCRYPTION_KEY", "")

# Separate signing secret for the guest check-in link JWT — never shares trust
# with users-ms's session auth. Own claims: {booking_id, exp}.
checkin_token_secret = os.environ.get("CHECKIN_TOKEN_SECRET", "")
checkin_token_grace_days = int(os.environ.get("CHECKIN_TOKEN_GRACE_DAYS", "1"))

# Shared secret required on /internal/* endpoints, injected only into the k8s
# CronJob pod env — never exposed through Traefik.
internal_cron_secret = os.environ.get("INTERNAL_CRON_SECRET", "")

# Days before start_date the check-in email is dispatched (inequality, not
# exact-match — catches last-minute bookings on the next daily sweep).
checkin_dispatch_lead_days = int(os.environ.get("CHECKIN_DISPATCH_LEAD_DAYS", "2"))

# Days past end_date before GuestIdentity sensitive fields are purged.
booking_purge_window_days = int(os.environ.get("BOOKING_PURGE_WINDOW_DAYS", "14"))
# Fallback max advance-booking window (days) when a property doesn't report one.
# Kept in sync with properties-ms; properties-ms is the source of truth per property.
BOOKING_WINDOW_DAYS = int(os.environ.get("BOOKING_WINDOW_DAYS", "180"))

# External calendar sync (BTR-41). The CronJob cadence itself lives in infra
# (CALENDAR_SYNC_POLL_MINUTES on the k8s CronJob schedule); these gate app behaviour.
calendar_sync_fetch_timeout = float(os.environ.get("CALENDAR_SYNC_FETCH_TIMEOUT", "10"))
calendar_sync_jitter_ms = int(os.environ.get("CALENDAR_SYNC_JITTER_MS", "500"))
# Hard cap on a fetched iCal body — feeds beyond this are rejected before parsing
# so a malicious/misconfigured origin can never OOM the pod. Booking.com/Airbnb
# exports for a single unit are a few KB; 5 MiB is a very generous ceiling.
calendar_sync_max_bytes = int(os.environ.get("CALENDAR_SYNC_MAX_BYTES", str(5 * 1024 * 1024)))
# Calendar dates in feeds without an explicit time are interpreted in this zone.
# Booking.com/Airbnb exports are all-day VALUE=DATE (tz-independent); this only
# affects the defensive down-convert of a stray DATE-TIME value. Platform-wide
# because parsing happens before the per-property lookup.
calendar_local_tz = os.environ.get("CALENDAR_LOCAL_TZ", "Europe/Sofia")
