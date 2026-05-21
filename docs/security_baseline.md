# Security Baseline

## Non-negotiables

1. Stream keys must never be stored in browser localStorage.
2. Stream keys must be encrypted at rest.
3. Stream keys must be scoped to an organization.
4. Stream keys must never be returned to the frontend in full.
5. Every stream start, stop, key rotation, and login event should create an audit event.
6. Production `.env` files must never be committed to GitHub.

## Environment Variables

```env
PENTECOSTAL_LIVE_ENV=development
PENTECOSTAL_LIVE_DB_URL=postgresql+psycopg://postgres:postgres@localhost:5432/pentecostal_live
PENTECOSTAL_LIVE_JWT_SECRET=replace_me
PENTECOSTAL_LIVE_FERNET_KEY=replace_me_generated_with_cryptography
PENTECOSTAL_LIVE_API_CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
```

## Fernet Key Generation

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```
