#!/bin/sh
set -eu

POSTGRES_HOST="${POSTGRES_HOST:-db}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_DB="${POSTGRES_DB:-ticketmaster}"
POSTGRES_USER="${POSTGRES_USER:-ticketmaster}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-ticketmaster}"

mkdir -p /etc/pgbouncer /var/run/pgbouncer

cat > /etc/pgbouncer/userlist.txt <<EOF
"${POSTGRES_USER}" "${POSTGRES_PASSWORD}"
EOF

cat > /etc/pgbouncer/pgbouncer.ini <<EOF
[databases]
${POSTGRES_DB} = host=${POSTGRES_HOST} port=${POSTGRES_PORT} dbname=${POSTGRES_DB}

[pgbouncer]
listen_addr = 0.0.0.0
listen_port = 6432
auth_type = plain
auth_file = /etc/pgbouncer/userlist.txt
pool_mode = transaction
max_client_conn = ${PGBOUNCER_MAX_CLIENT_CONN:-500}
default_pool_size = ${PGBOUNCER_DEFAULT_POOL_SIZE:-25}
reserve_pool_size = ${PGBOUNCER_RESERVE_POOL_SIZE:-5}
server_idle_timeout = 300
ignore_startup_parameters = extra_float_digits
admin_users = ${POSTGRES_USER}
stats_users = ${POSTGRES_USER}
EOF

exec pgbouncer -u nobody /etc/pgbouncer/pgbouncer.ini
