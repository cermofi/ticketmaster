FROM alpine:3.20

RUN apk add --no-cache pgbouncer postgresql-client

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

EXPOSE 6432
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
