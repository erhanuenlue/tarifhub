# syntax=docker/dockerfile:1
# Multi-stage Node build for MeldePilot (Next.js App Router, standalone output).

# --- deps: install dependencies against the lockfile ---
FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci

# --- build: compile the Next.js standalone server ---
FROM node:22-alpine AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# --- runtime: minimal, non-root ---
FROM node:22-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3002
# SERVING_BASE_URL + TARIFIQ_BASE_URL are injected at deploy time (Helm / compose).

RUN addgroup -g 10001 meldepilot && adduser -u 10001 -G meldepilot -D meldepilot

# Next.js `output: "standalone"` emits a self-contained server + the minimal node_modules.
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
COPY --from=build /app/public ./public

USER meldepilot
EXPOSE 3002
CMD ["node", "server.js"]
