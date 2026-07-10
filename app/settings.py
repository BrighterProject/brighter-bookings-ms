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
