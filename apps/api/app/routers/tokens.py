"""Refresh-token endpoints: rotate access/refresh pairs and revoke on logout."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.audit import record_audit_event
from app.core.security import create_access_token
from app.db import get_db
from app.token_store import find_valid_refresh_token, issue_refresh_token, revoke_refresh_token


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/refresh", response_model=schemas.TokenResponse)
def refresh(payload: schemas.RefreshRequest, db: Session = Depends(get_db)) -> schemas.TokenResponse:
    """Rotate a refresh token: revoke the presented one, issue a new pair."""
    token = find_valid_refresh_token(db, payload.refresh_token)
    if token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token")

    user = db.get(models.User, token.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token")

    revoke_refresh_token(token)
    new_refresh_token = issue_refresh_token(db, token.user_id, token.organization_id)
    access_token = create_access_token(token.user_id, token.organization_id)
    db.commit()
    return schemas.TokenResponse(access_token=access_token, refresh_token=new_refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(payload: schemas.RefreshRequest, db: Session = Depends(get_db)) -> None:
    """Revoke the presented refresh token. Idempotent: unknown tokens are a no-op."""
    token = find_valid_refresh_token(db, payload.refresh_token)
    if token is not None:
        revoke_refresh_token(token)
        record_audit_event(
            db,
            event_type="auth.logged_out",
            organization_id=token.organization_id,
            actor_user_id=token.user_id,
        )
        db.commit()
    return None
