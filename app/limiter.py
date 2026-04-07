import os

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.settings import REDIS_URL

# When SLOWAPI_NO_LIMITS is set (e.g. in tests) skip Redis storage entirely
# so the limiter never opens a connection.
_storage_uri = None if os.environ.get("SLOWAPI_NO_LIMITS") else REDIS_URL
limiter = Limiter(key_func=get_remote_address, storage_uri=_storage_uri)
