# Pentecostal Live — Phase 1 Foundation

Pentecostal Live is being structured as a broadcast operating system, proven first through PMBC and built for later multi-church, multi-campus deployment.

## Phase 1 Goal
Turn the current prototype into a real software foundation by adding:

1. Monorepo structure
2. PostgreSQL database model
3. Organization-aware authentication
4. Encrypted platform stream keys
5. API versioning
6. CI/CD deployment path
7. Secure environment standards

## Monorepo Layout

```text
pentecostal-live/
  apps/
    dashboard/        Next.js dashboard replacing dashboard.html
    api/              FastAPI backend promoted from app/main.py
    media-server/     Media server promoted from media_server/server.py
  packages/
    types/            Shared API and frontend types
    ui/               Shared components and church/tribe design system
    config/           Environment schemas and platform definitions
  services/
    ffmpeg/           FFmpeg command builder
    rtmp/             RTMP destination and connection logic
    hls/              HLS transcode and PMBC website streaming
  infra/
    docker/           Dockerfiles and compose files
    nginx/            NGINX/RTMP/HLS configs
    .github/workflows CI/CD workflows
  docs/               Architecture, schema, security notes
```

## Current Build

This repo now contains a runnable Phase 1 slice:

- `apps/api`: FastAPI backend with `/v1` auth, organizations, platform keys, streams, and websocket handshake routes.
- `apps/dashboard`: Next.js dashboard for login/register, platform key management, stream scheduling, start/stop, and scene switching.
- `packages/types`: Shared TypeScript API contracts used by the dashboard.
- `packages/config`: Shared platform definitions for YouTube, Facebook, TikTok, Instagram, and PMBC website output.
- `packages/ui`: Initial brand token package for the church/tribe design system.
- `infra/docker`: PostgreSQL and API compose setup.
- `.github/workflows`: CI jobs for API tests and dashboard checks.

## Local Development

Create an environment file:

```bash
cp .env.example .env
```

Start PostgreSQL and the API through Docker:

```bash
docker compose -f infra/docker/docker-compose.yml up --build
```

Or run the API directly:

```bash
cd apps/api
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Run the dashboard:

```bash
npm install
npm run dev:dashboard
```

Open:

- API health: `http://localhost:8000/health`
- API docs: `http://localhost:8000/v1/docs`
- Dashboard: `http://localhost:3000`

## First Build Order

1. Move existing files into the monorepo.
2. Add PostgreSQL and SQLAlchemy/Alembic.
3. Create six core tables: organizations, users, roles, memberships, platform_keys, streams.
4. Encrypt stream keys before storage.
5. Replace dashboard localStorage stream keys with API calls. [done]
6. Add JWT login and org-scoped access.
7. Add GitHub Actions for lint/test.

## Security Gate

No real PMBC, YouTube, Facebook, TikTok, Instagram, or website stream keys should be stored in browser localStorage. Keys must be encrypted at rest, scoped to an organization, and never returned in full to the frontend.
