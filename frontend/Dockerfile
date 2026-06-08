FROM node:22-alpine AS build

WORKDIR /app
COPY frontend/package.json package.json
RUN npm install
COPY frontend/index.html frontend/vite.config.js /app/
COPY frontend/public /app/public
COPY frontend/src /app/src
RUN npm run build

FROM python:3.12-alpine AS docs

WORKDIR /app
COPY docs/requirements.txt docs/requirements.txt
RUN pip install --no-cache-dir -r docs/requirements.txt
COPY mkdocs.yml mkdocs.yml
COPY docs /app/docs
RUN mkdocs build --site-dir /app/site

FROM nginx:1.27-alpine
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
COPY --from=docs /app/site /usr/share/nginx/html/docs
EXPOSE 80
