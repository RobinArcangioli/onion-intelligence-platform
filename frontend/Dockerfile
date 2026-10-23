FROM node:22-alpine AS build
WORKDIR /frontend
COPY frontend/package*.json ./
# If a release lockfile is available, prefer reproducible npm ci.
# RC1 still supports upgrades from earlier archives without package-lock.json.
RUN if [ -f package-lock.json ]; then npm ci --no-audit --no-fund; else npm install --no-audit --no-fund; fi
COPY frontend/tsconfig.json frontend/vite.config.ts frontend/index.html ./
COPY frontend/src ./src
RUN npm run build

FROM nginxinc/nginx-unprivileged:stable-alpine
COPY --from=build /frontend/dist /usr/share/nginx/html
COPY infrastructure/nginx/default.conf /etc/nginx/conf.d/default.conf
