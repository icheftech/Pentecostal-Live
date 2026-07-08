"""Refresh-token persistence helpers.

Only a SHA-256 hash of each refresh token is stored; the raw token is
returned to the client exactly once and can never be recovered from the DB.
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.core.config import get_settings


def hash_refresh_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


def issue_refresh_token(db: Session, user_id: str, organization_id: str) -> str:
    """Create and persist a refresh token row; returns the raw token.

    The caller is responsible for committing the session.
    """
    raw_token = secrets.token_urlsafe(48)
    expires_at = datetime.now(UTC) + timedelta(days=get_settings().refresh_token_days)
    db.add(
        models.RefreshToken(
            user_id=user_id,
            organization_id=organization_id,
            token_hash=hash_refresh_token(raw_token),
            expires_at=expires_at,
        )
    )
    return raw_token


def find_valid_refresh_token(db: Session, raw_token: str) -> models.RefreshToken | None:
    """Return the matching, unrevoked, unexpired refresh token row, or None."""
    token = db.scalar(
        select(models.RefreshToken).where(models.RefreshToken.token_hash == hash_refresh_token(raw_token))
    )
    if token is None or token.revoked_at is not None:
        return None
    expires_at = token.expires_at
    if expires_at.tzinfo is None:  # SQLite returns naive datetimes
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= datetime.now(UTC):
        return None
    return token


def revoke_refresh_token(token: models.RefreshToken) -> None:
    token.revoked_at = datetime.now(UTC)
