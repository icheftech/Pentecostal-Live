"""Test bootstrap.

Must run before any test module imports ``app.*``: environment overrides here
feed the cached ``Settings`` object created on first import.

- Rate limiting is disabled (``PENTECOSTAL_LIVE_RATE_LIMIT_ENABLED=false``) so
  TestClient loops over auth endpoints do not trip the per-IP limiter.
- Tables are created from SQLAlchemy metadata (``create_all`` is a no-op for
  tables that already exist), matching how the suite has always run against
  the default SQLite database. In CI, Alembic migrations run first against
  Postgres and this remains a no-op.
"""

import os


os.environ.setdefault("PENTECOSTAL_LIVE_RATE_LIMIT_ENABLED", "false")

from app import models  # noqa: F401, E402  (register models on Base.metadata)
from app.db import Base, engine  # noqa: E402


Base.metadata.create_all(bind=engine)
