# Copyright 2026 Core Odoo contributors — SPDX-License-Identifier: Apache-2.0
# syntax=docker/dockerfile:1

FROM node:24-alpine AS build
WORKDIR /app

COPY package.json package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

COPY . .
RUN npm run build

FROM nginx:1.30.6-alpine AS runtime
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
HEALTHCHECK --interval=5s --timeout=3s --retries=3 --start-period=3s \
  CMD wget -qO- http://127.0.0.1/healthz >/dev/null || exit 1
