from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.core.security import decode_access_token
from app.db import get_db


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/v1/auth/login")


@dataclass
class CurrentContext:
    user: models.User
    organization: models.Organization
    role: models.Role


def get_current_context(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> CurrentContext:
    try:
        payload = decode_access_token(token)
        user_id = str(payload["sub"])
        organization_id = str(payload["org"])
    except (KeyError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
        )

    result = db.execute(
        select(models.User, models.Organization, models.Role)
        .join(models.Membership, models.Membership.user_id == models.User.id)
        .join(models.Organization, models.Organization.id == models.Membership.organization_id)
        .join(models.Role, models.Role.id == models.Membership.role_id)
        .where(models.User.id == user_id)
        .where(models.Organization.id == organization_id)
        .where(models.User.is_active.is_(True))
    ).first()

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
        )

    user, organization, role = result
    return CurrentContext(user=user, organization=organization, role=role)

