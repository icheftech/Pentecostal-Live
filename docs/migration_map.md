# Migration Map From Current ZIP

Current file -> New location

- `dashboard.html` -> `apps/dashboard/` as Next.js routes/components
- `app/main.py` -> `apps/api/app/main.py`
- `media_server/server.py` -> `apps/media-server/server.py`
- `media_server/nginx.conf.example` -> `infra/nginx/nginx.conf.example`
- `media_server/website_embed.html` -> `apps/dashboard/components/website_embed_preview.tsx`
- `test_backend.py` -> `apps/api/tests/test_backend.py`
- `requirements.txt` -> `apps/api/requirements.txt`
- `.env.example` -> root `.env.example` with namespaced env vars

## Do Not Carry Forward

- Do not keep stream keys in localStorage.
- Do not keep all stream state only in memory.
- Do not expose unmasked stream keys through API responses.
