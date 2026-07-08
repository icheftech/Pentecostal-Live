"""Shared slowapi rate limiter.

Lives in its own module so routers can import it without importing
``app.main`` (which would create a circular import). Disabled entirely when
``PENTECOSTAL_LIVE_RATE_LIMIT_ENABLED=false`` (used by the test suite).
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import get_settings


limiter = Limiter(
    key_func=get_remote_address,
    enabled=get_settings().rate_limit_enabled,
)
