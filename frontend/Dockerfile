FROM node:22-alpine AS build

WORKDIR /app
ARG APP_VERSION=dev-local
ENV VITE_APP_VERSION=${APP_VERSION}
COPY frontend/package.json package.json
RUN npm install
COPY frontend/index.html frontend/vite.config.js /app/
COPY frontend/public /app/public
COPY frontend/src /app/src
RUN npm run build

FROM nginx:1.27-alpine
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
