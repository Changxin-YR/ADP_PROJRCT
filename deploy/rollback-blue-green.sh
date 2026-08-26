#!/usr/bin/env bash
set -Eeuo pipefail
umask 027

[[ "$(id -u)" == "0" ]] || { echo "run as root" >&2; exit 1; }
exec 9>/run/lock/adp-blue-green.lock
flock -n 9 || { echo "another ADP deployment is running" >&2; exit 1; }

STATE_ROOT=/var/lib/adp/deployments
NGINX_LIVE=/etc/nginx/conf.d/adp-auth.conf
MYSQL_CNF=""
cleanup() {
  [[ -z "$MYSQL_CNF" || ! -f "$MYSQL_CNF" ]] || rm -f -- "$MYSQL_CNF"
}
trap cleanup EXIT

env_value() {
  local key="$1" line value
  line="$(grep -m1 -E "^${key}=" /etc/adp/auth.env)" || { echo "missing $key" >&2; return 1; }
  value="${line#*=}"
  if [[ "$value" == \"* && "$value" == *\" ]]; then value="${value:1:${#value}-2}"; fi
  if [[ "$value" == \'* && "$value" == *\' ]]; then value="${value:1:${#value}-2}"; fi
  printf '%s' "$value"
}

MYSQL_HOST="$(env_value MYSQL_HOST)"
MYSQL_PORT="$(env_value MYSQL_PORT)"
MYSQL_USER="$(env_value MYSQL_USER)"
MYSQL_PASSWORD="$(env_value MYSQL_PASSWORD)"
MYSQL_DATABASE="$(env_value MYSQL_DATABASE)"
MYSQL_CNF="$(mktemp /etc/adp/mysql-rollback.XXXXXX)"
chmod 600 "$MYSQL_CNF"
{
  echo '[client]'
  printf 'host=%s\nport=%s\nuser=%s\npassword=%s\n' "$MYSQL_HOST" "$MYSQL_PORT" "$MYSQL_USER" "$MYSQL_PASSWORD"
} > "$MYSQL_CNF"
invalid="$(mysql --defaults-extra-file="$MYSQL_CNF" --database="$MYSQL_DATABASE" --batch --skip-column-names --execute="SELECT COUNT(*) FROM role_permissions rp INNER JOIN roles r ON r.id=rp.role_id INNER JOIN permissions p ON p.id=rp.permission_id WHERE r.code='breed_manager' AND p.code IN ('auth.review','auth.user.manage')")"
[[ "$invalid" == "0" ]] || { echo "legacy role permission smoke failed" >&2; exit 1; }

RELEASE_ID="${1:-$(find "$STATE_ROOT" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort | tail -1)}"
STATE_DIR="$STATE_ROOT/$RELEASE_ID"
PREVIOUS="$STATE_DIR/previous-nginx.conf"
[[ -f "$PREVIOUS" ]] || { echo "previous-nginx.conf not found for $RELEASE_ID" >&2; exit 1; }

temporary=/etc/nginx/conf.d/.adp-auth.conf.rollback
install -o root -g root -m 0644 "$PREVIOUS" "$temporary"
mv -f -- "$temporary" "$NGINX_LIVE"
nginx -t
systemctl reload nginx
curl --fail --silent --show-error http://127.0.0.1:5001/api/v1/health >/dev/null

server_name="$(awk -F= '$1=="ADP_SERVER_NAME" {sub(/^[^=]*=/, ""); print; exit}' /etc/adp/auth.env)"
curl --fail --silent --show-error --resolve "$server_name:443:127.0.0.1" "https://$server_name/healthz" >/dev/null
date --iso-8601=seconds > "$STATE_DIR/rolled-back-at"
echo "traffic rolled back for $RELEASE_ID; databases and green service were preserved"
