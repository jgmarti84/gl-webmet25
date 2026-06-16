#!/bin/sh
set -eu

ADMIN_USERNAME="${ADMIN_USERNAME:-admin}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-change-me}"

htpasswd -bc /etc/nginx/admin.htpasswd "${ADMIN_USERNAME}" "${ADMIN_PASSWORD}" >/dev/null 2>&1

exec "$@"
