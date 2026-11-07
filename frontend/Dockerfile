FROM node:24-alpine@sha256:a34ab6d7f6f4813f4d0c5469d74685604b962fbdbf5793a7bc7b4998ecb867c8 AS build
WORKDIR /frontend
COPY scripts/install-locked-npm.sh /tmp/install-locked-npm.sh
RUN sh /tmp/install-locked-npm.sh && rm /tmp/install-locked-npm.sh
COPY frontend/package.json frontend/package-lock.json ./
# Fail the build if package-lock.json is missing or out of sync.
RUN npm ci --no-audit --no-fund
COPY frontend/tsconfig.json frontend/vite.config.ts frontend/index.html ./
COPY frontend/src ./src
RUN npm run build

FROM nginx/nginx-unprivileged:1.30.6-alpine@sha256:44e74ca483234093081138b6d7b6f561d55557756a2deefc3a5056148defeb99
USER root
RUN apk add --no-cache libexpat=2.10.0-r0
USER 101
COPY --from=build /frontend/dist /usr/share/nginx/html
COPY infrastructure/nginx/default.conf /etc/nginx/conf.d/default.conf
