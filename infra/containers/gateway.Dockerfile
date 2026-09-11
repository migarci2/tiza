FROM node:24.12.0-alpine AS web
WORKDIR /web
RUN corepack enable && corepack prepare pnpm@11.5.3 --activate
COPY apps/web/package.json apps/web/pnpm-lock.yaml apps/web/pnpm-workspace.yaml ./
RUN corepack pnpm install --frozen-lockfile
COPY apps/web ./
RUN corepack pnpm build
FROM caddy:2.10.2-alpine
COPY --from=web /web/dist /srv
COPY infra/caddy/Caddyfile /etc/caddy/Caddyfile
