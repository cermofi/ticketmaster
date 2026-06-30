FROM node:22-alpine AS build

WORKDIR /app
ARG APP_VERSION=dev-local
ENV VITE_APP_VERSION=${APP_VERSION}
COPY package.json package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci --prefer-offline --no-audit; else npm install --no-audit; fi
COPY index.html vite.config.js /app/
COPY public /app/public
COPY src /app/src
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
