#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

if [[ "$(id -u)" != "0" ]]; then
  echo "请使用 root 执行此脚本。" >&2
  exit 1
fi

APP_ROOT="${APP_ROOT:-/opt/adp/login-registration}"
[[ "$APP_ROOT" == /opt/adp/login-registration && ! -L "$APP_ROOT" ]] || exit 1
LATEST_BACKUP="${ADP_ROLLBACK_BACKUP:?Select an explicit pre-release backup}"
[[ "$LATEST_BACKUP" =~ ^/opt/adp/backups/[A-Za-z0-9._-]+$ && ! -L "$LATEST_BACKUP" ]] || exit 1
ENV_FILE="${ADP_DEPLOY_ENV_FILE:-/etc/adp/auth.env}"
SERVICE="${ADP_DEPLOY_SERVICE:-adp-auth}"
BACKEND_PORT="${ADP_BACKEND_PORT:-5001}"
[[ "$ENV_FILE" == /etc/adp/auth.env || "$ENV_FILE" == /etc/adp/next.env ]] || exit 1
[[ "$SERVICE" == adp-auth || "$SERVICE" == adp-next ]] || exit 1
[[ "$BACKEND_PORT" == 5001 || "$BACKEND_PORT" == 5002 ]] || exit 1
exec 9>/run/lock/adp-canonical-deploy.lock
flock -n 9 || exit 1

for directory in backend frontend database; do
  test -d "$LATEST_BACKUP/$directory" && test -d "$APP_ROOT/$directory" || exit 1
  [[ ! -L "$LATEST_BACKUP/$directory" && ! -L "$APP_ROOT/$directory" ]] || exit 1
done
test -f "$LATEST_BACKUP/nginx.conf" || exit 1
# shellcheck disable=SC1090
source "$ENV_FILE"
NGINX_TARGET=/etc/nginx/conf.d/adp-auth.conf
if [[ "${ADP_NGINX_MODE:-standalone}" == shared ]]; then
  NGINX_TARGET=/etc/nginx/snippets/adp-location.conf
fi
FAILED_DIR="$(mktemp -d /opt/adp/backups/rollback-displaced.XXXXXX)"
cp -a "$NGINX_TARGET" "$FAILED_DIR/nginx.conf"
restore_on_error() {
  local status=$?
  if (( status != 0 )); then
    for directory in backend frontend database; do
      if [[ -d "$FAILED_DIR/$directory" ]]; then
        if [[ -d "$APP_ROOT/$directory" ]]; then
          mv -- "$APP_ROOT/$directory" "$FAILED_DIR/unsuccessful-$directory"
        fi
        mv -- "$FAILED_DIR/$directory" "$APP_ROOT/$directory"
      fi
    done
    cp -a "$FAILED_DIR/nginx.conf" "$NGINX_TARGET"
    systemctl restart "$SERVICE" || true
    nginx -t && systemctl reload nginx
  fi
  exit "$status"
}
trap restore_on_error EXIT

systemctl stop "$SERVICE"
for directory in backend frontend database; do
  mv -- "$APP_ROOT/$directory" "$FAILED_DIR/$directory"
  cp -a "$LATEST_BACKUP/$directory" "$APP_ROOT/$directory"
done
install -m 0644 "$LATEST_BACKUP/nginx.conf" "$NGINX_TARGET"
nginx -t
systemctl restart "$SERVICE"
systemctl reload nginx
curl --retry 10 --retry-connrefused --retry-delay 1 --fail --silent --show-error -H "Host: $ADP_SERVER_NAME" "http://127.0.0.1:$BACKEND_PORT/api/v1/health" >/dev/null
echo "Application restored from $LATEST_BACKUP; displaced files retained in $FAILED_DIR. Database migrations were not reversed."
