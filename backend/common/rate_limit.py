"""Rate limiting configuration using slowapi.

Provides a module-level Limiter instance that can be imported by routers
for per-endpoint rate limiting, and wired into the FastAPI app in main.py.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

# Default: 60 requests/minute per client IP for all endpoints.
# Individual routes can override with @limiter.limit("N/period").
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["60/minute"],
)
