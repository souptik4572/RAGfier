# syntax=docker/dockerfile:1.7
# ─────────────────────────────────────────────────────────────────────────────
# RAGfier frontend — production multi-stage build
# Produces a minimal Next.js standalone server image (~180MB).
# ─────────────────────────────────────────────────────────────────────────────

# ── Stage 1: install full dependency tree (incl. devDependencies for build) ─
FROM node:22-alpine AS deps
WORKDIR /app

# libc6-compat is required for some Next.js native modules on alpine
RUN apk add --no-cache libc6-compat

COPY package.json package-lock.json* ./
RUN npm ci --no-audit --no-fund

# ── Stage 2: build Next.js app in standalone mode ────────────────────────────
FROM node:22-alpine AS builder
WORKDIR /app

RUN apk add --no-cache libc6-compat

COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Disable telemetry and any build-time network calls we don't need
ENV NEXT_TELEMETRY_DISABLED=1
ENV NODE_ENV=production

# NEXT_PUBLIC_API_URL is baked into the client bundle at build time. Callers
# should pass `--build-arg NEXT_PUBLIC_API_URL=...` when the default is wrong.
ARG NEXT_PUBLIC_API_URL=http://backend:8000
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}

# Allowed upload extensions are also inlined into browser bundles at build time.
ARG NEXT_PUBLIC_ALLOWED_FILE_EXTENSIONS=.pdf,.md,.markdown
ENV NEXT_PUBLIC_ALLOWED_FILE_EXTENSIONS=${NEXT_PUBLIC_ALLOWED_FILE_EXTENSIONS}

RUN npm run build

# ── Stage 3: runtime image — only what's needed to serve ─────────────────────
FROM node:22-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

# Run as a non-root user
RUN addgroup --system --gid 1001 nodejs \
 && adduser --system --uid 1001 nextjs

# Public assets and standalone server bundle
COPY --from=builder --chown=nextjs:nodejs /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000

# Basic container healthcheck — hits the Next.js server root
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD wget -qO- --tries=1 --spider http://127.0.0.1:3000/ || exit 1

CMD ["node", "server.js"]
