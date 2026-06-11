# syntax=docker/dockerfile:1
# Multi-stage Node build for TarifGuard (Next.js App Router, standalone output).

# --- deps: install dependencies against the lockfile ---
# Base image pinned by digest 2026-06-11 (node:22-alpine manifest-list digest).
FROM node:22-alpine@sha256:9385cd9f3001dfc3431e8ead12c43e9e1f87cc1b9b5c6cfd0f73865d405b27c4 AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci

# --- build: compile the Next.js standalone server ---
# Base image pinned by digest 2026-06-11 (node:22-alpine manifest-list digest).
FROM node:22-alpine@sha256:9385cd9f3001dfc3431e8ead12c43e9e1f87cc1b9b5c6cfd0f73865d405b27c4 AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# --- runtime: minimal, non-root ---
# Base image pinned by digest 2026-06-11 (node:22-alpine manifest-list digest).
FROM node:22-alpine@sha256:9385cd9f3001dfc3431e8ead12c43e9e1f87cc1b9b5c6cfd0f73865d405b27c4 AS runtime
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000
# SERVING_BASE_URL is injected at deploy time (Helm / compose); never baked in.

RUN addgroup -g 10001 tarifguard && adduser -u 10001 -G tarifguard -D tarifguard

# Next.js `output: "standalone"` emits a self-contained server + the minimal node_modules.
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
COPY --from=build /app/public ./public

USER tarifguard
EXPOSE 3000
CMD ["node", "server.js"]
