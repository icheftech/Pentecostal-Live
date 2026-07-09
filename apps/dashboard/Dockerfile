# Dashboard image (npm workspaces).
# Build from the REPO ROOT so the workspace tree is in context:
#   docker build -f apps/dashboard/Dockerfile \
#     --build-arg NEXT_PUBLIC_API_BASE_URL=https://api.example.com .

# ---------------------------------------------------------------------------
# deps: install workspace dependencies from lockfile
# ---------------------------------------------------------------------------
FROM node:20-alpine AS deps
WORKDIR /repo

COPY package.json package-lock.json ./
COPY apps/dashboard/package.json apps/dashboard/
COPY packages/types/package.json packages/types/
COPY packages/ui/package.json packages/ui/
COPY packages/config/package.json packages/config/

RUN npm ci

# ---------------------------------------------------------------------------
# builder: build the Next.js app (standalone output)
# ---------------------------------------------------------------------------
FROM node:20-alpine AS builder
WORKDIR /repo

# NEXT_PUBLIC_* vars are inlined at build time.
ARG NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL}
ARG NEXT_PUBLIC_MEDIA_SERVER_URL=http://localhost:8001
ENV NEXT_PUBLIC_MEDIA_SERVER_URL=${NEXT_PUBLIC_MEDIA_SERVER_URL}
ENV NEXT_TELEMETRY_DISABLED=1

COPY --from=deps /repo/node_modules ./node_modules
COPY package.json package-lock.json ./
COPY packages ./packages
COPY apps/dashboard ./apps/dashboard

RUN npm run build

# ---------------------------------------------------------------------------
# runner: slim runtime with only the standalone server
# ---------------------------------------------------------------------------
FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV PORT=3000
ENV HOSTNAME=0.0.0.0
ENV NEXT_TELEMETRY_DISABLED=1

# Standalone output mirrors the monorepo layout: server.js sits under
# .next/standalone/apps/dashboard/ with a pruned node_modules at the root.
COPY --from=builder /repo/apps/dashboard/.next/standalone ./
COPY --from=builder /repo/apps/dashboard/.next/static ./apps/dashboard/.next/static

USER node
EXPOSE 3000
CMD ["node", "apps/dashboard/server.js"]
