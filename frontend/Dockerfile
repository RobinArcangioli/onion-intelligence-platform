FROM node:22-alpine AS build
WORKDIR /frontend
COPY frontend/package*.json ./
# Fail the build if package-lock.json is missing or out of sync.
RUN npm ci --no-audit --no-fund
COPY frontend/tsconfig.json frontend/vite.config.ts frontend/index.html ./
COPY frontend/src ./src
RUN npm run build

FROM nginxinc/nginx-unprivileged:stable-alpine
COPY --from=build /frontend/dist /usr/share/nginx/html
COPY infrastructure/nginx/default.conf /etc/nginx/conf.d/default.conf
