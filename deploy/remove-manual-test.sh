#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

[[ "$(id -u)" == "0" ]] || { echo "run as root" >&2; exit 1; }
exec 9>/run/lock/adp-blue-green.lock
flock -n 9 || { echo "another ADP manual test operation is running" >&2; exit 1; }

EXPECTED_DATABASE=adp_manual_test_20260817
CONFIRMATION=DELETE_MANUAL_TEST_ENVIRONMENT
DATABASE="${1:-}"
[[ $# == 2 && "$DATABASE" == "$EXPECTED_DATABASE" && "$2" == "$CONFIRMATION" ]] || {
  echo "usage: $0 adp_manual_test_20260817 DELETE_MANUAL_TEST_ENVIRONMENT" >&2
  exit 2
}

TEST_ENV=/etc/adp/manual-test.env
CREDENTIALS=/etc/adp/manual-test-credentials.env
NGINX_LIVE=/etc/nginx/conf.d/adp-auth.conf
SERVICE_FILE=/etc/systemd/system/adp-manual-test.service
TEST_ROOT=/var/lib/adp/manual-test-20260817
ATTACHMENTS=/var/lib/adp/manual-test-20260817/attachments
PREVIOUS_NGINX=/var/lib/adp/manual-test-20260817/previous-nginx.conf
MANUAL_NGINX=/var/lib/adp/manual-test-20260817/new-nginx.conf
TEST_DB_USER=adp_manual_test_20260817

[[ -f "$TEST_ENV" && -f "$PREVIOUS_NGINX" && -f "$MANUAL_NGINX" ]] || {
  echo "manual test environment state is missing" >&2; exit 1;
}
configured_database="$(grep -m1 '^MYSQL_DATABASE=' "$TEST_ENV" | cut -d= -f2-)"
[[ "$configured_database" == "$EXPECTED_DATABASE" ]] || {
  echo "configured database does not match fixed manual test target" >&2; exit 1;
}
expected_nginx_sha="$(sha256sum "$MANUAL_NGINX" | awk '{print $1}')"
current_nginx_sha="$(sha256sum "$NGINX_LIVE" | awk '{print $1}')"
[[ "$current_nginx_sha" == "$expected_nginx_sha" ]] || {
  echo "nginx configuration changed since manual test installation" >&2; exit 1;
}

temporary_nginx=/etc/nginx/conf.d/.adp-auth.conf.manual-test-remove
install -o root -g root -m 0644 "$PREVIOUS_NGINX" "$temporary_nginx"
mv -f -- "$temporary_nginx" "$NGINX_LIVE"
nginx -t
systemctl reload nginx
curl --fail --silent --show-error http://127.0.0.1:5002/api/v1/health | grep -q '"environment":"production"'

systemctl stop adp-manual-test
systemctl disable adp-manual-test
rm -f -- "$SERVICE_FILE"
systemctl daemon-reload

mysql --execute="DROP DATABASE \`${DATABASE}\`; DROP USER IF EXISTS '${TEST_DB_USER}'@'localhost'; DROP USER IF EXISTS '${TEST_DB_USER}'@'127.0.0.1'"
rm -f -- "$TEST_ENV" "$CREDENTIALS"
rm -rf -- "$ATTACHMENTS"
rm -rf -- "$TEST_ROOT"

echo "manual test environment removed; production remains active"
