from datetime import UTC, datetime, timedelta
from typing import Any

from cryptography.fernet import Fernet
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def create_access_token(subject: str, organization_id: str) -> str:
    settings = get_settings()
    expires_at = datetime.now(UTC) + timedelta(minutes=settings.access_token_minutes)
    payload: dict[str, Any] = {
        "sub": subject,
        "org": organization_id,
        "exp": expires_at,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise ValueError("Invalid access token") from exc


def encrypt_stream_key(stream_key: str) -> str:
    return Fernet(get_settings().fernet_key.encode()).encrypt(stream_key.encode()).decode()


def decrypt_stream_key(encrypted_stream_key: str) -> str:
    return Fernet(get_settings().fernet_key.encode()).decrypt(encrypted_stream_key.encode()).decode()


def mask_stream_key(stream_key: str | None) -> str:
    if not stream_key:
        return "********"
    return f"********{stream_key[-4:]}"

