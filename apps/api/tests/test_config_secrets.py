import pytest

from app.core.config import DEFAULT_FERNET_KEY, DEFAULT_JWT_SECRET, Settings


def clear_secret_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PENTECOSTAL_LIVE_JWT_SECRET", raising=False)
    monkeypatch.delenv("PENTECOSTAL_LIVE_FERNET_KEY", raising=False)


def test_development_allows_default_secrets(monkeypatch):
    clear_secret_env(monkeypatch)
    monkeypatch.setenv("PENTECOSTAL_LIVE_ENV", "development")
    settings = Settings(_env_file=None)
    assert settings.jwt_secret == DEFAULT_JWT_SECRET
    assert settings.fernet_key == DEFAULT_FERNET_KEY


def test_test_environment_allows_default_secrets(monkeypatch):
    clear_secret_env(monkeypatch)
    monkeypatch.setenv("PENTECOSTAL_LIVE_ENV", "test")
    settings = Settings(_env_file=None)
    assert settings.jwt_secret == DEFAULT_JWT_SECRET


def test_production_rejects_default_secrets(monkeypatch):
    clear_secret_env(monkeypatch)
    monkeypatch.setenv("PENTECOSTAL_LIVE_ENV", "production")
    with pytest.raises(RuntimeError, match="PENTECOSTAL_LIVE_JWT_SECRET"):
        Settings(_env_file=None)


def test_production_rejects_default_jwt_secret_alone(monkeypatch):
    clear_secret_env(monkeypatch)
    monkeypatch.setenv("PENTECOSTAL_LIVE_ENV", "production")
    monkeypatch.setenv("PENTECOSTAL_LIVE_FERNET_KEY", "a-real-fernet-key-set-by-ops")
    with pytest.raises(RuntimeError, match="PENTECOSTAL_LIVE_JWT_SECRET"):
        Settings(_env_file=None)


def test_production_rejects_default_fernet_key_alone(monkeypatch):
    clear_secret_env(monkeypatch)
    monkeypatch.setenv("PENTECOSTAL_LIVE_ENV", "production")
    monkeypatch.setenv("PENTECOSTAL_LIVE_JWT_SECRET", "a-real-jwt-secret-set-by-ops")
    with pytest.raises(RuntimeError, match="PENTECOSTAL_LIVE_FERNET_KEY"):
        Settings(_env_file=None)


def test_production_accepts_custom_secrets(monkeypatch):
    clear_secret_env(monkeypatch)
    monkeypatch.setenv("PENTECOSTAL_LIVE_ENV", "production")
    monkeypatch.setenv("PENTECOSTAL_LIVE_JWT_SECRET", "a-real-jwt-secret-set-by-ops")
    monkeypatch.setenv("PENTECOSTAL_LIVE_FERNET_KEY", "a-real-fernet-key-set-by-ops")
    settings = Settings(_env_file=None)
    assert settings.environment == "production"
    assert settings.jwt_secret != DEFAULT_JWT_SECRET
