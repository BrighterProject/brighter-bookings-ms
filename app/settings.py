import os

db_url = os.environ.get("DB_URL", "sqlite://:memory:")
users_ms_url = os.environ.get("USERS_MS_URL", "http://localhost:8000")
properties_ms_url = os.environ.get("PROPERTIES_MS_URL", "http://localhost:8001")
payments_ms_url = os.environ.get("PAYMENTS_MS_URL", "http://localhost:8003")
notifications_ms_url = os.environ.get("NOTIFICATIONS_MS_URL", "http://localhost:8004")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

# Fallback max advance-booking window (days) when a property doesn't report one.
# Kept in sync with properties-ms; properties-ms is the source of truth per property.
BOOKING_WINDOW_DAYS = int(os.environ.get("BOOKING_WINDOW_DAYS", "180"))
