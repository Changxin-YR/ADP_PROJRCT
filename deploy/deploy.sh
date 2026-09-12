#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

if [[ "$(id -u)" != "0" ]]; then
  echo "请使用 root 执行此脚本。" >&2
  exit 1
fi

APP_ROOT="${APP_ROOT:-/opt/adp/login-registration}"
[[ "$APP_ROOT" == /opt/adp/login-registration ]] || { echo "Unexpected deployment root" >&2; exit 1; }
ENV_FILE="${ADP_DEPLOY_ENV_FILE:-/etc/adp/auth.env}"
SERVICE="${ADP_DEPLOY_SERVICE:-adp-auth}"
BACKEND_PORT="${ADP_BACKEND_PORT:-5001}"
[[ "$ENV_FILE" == /etc/adp/auth.env || "$ENV_FILE" == /etc/adp/next.env ]] || exit 1
[[ "$SERVICE" == adp-auth || "$SERVICE" == adp-next ]] || exit 1
[[ "$BACKEND_PORT" == 5001 || "$BACKEND_PORT" == 5002 ]] || exit 1
exec 9>/run/lock/adp-canonical-deploy.lock
flock -n 9 || { echo "Deployment already running" >&2; exit 1; }
BACKEND_DIR="$APP_ROOT/backend"
FRONTEND_DIR="$APP_ROOT/frontend"
DEPLOY_DIR="$APP_ROOT/deploy"
PYTHON_BIN="${PYTHON_BIN:-/opt/adp-venv/bin/python}"
VENV_PIP="${VENV_PIP:-/opt/adp-venv/bin/pip}"
MYSQL_CNF=""
NGINX_CONFIG=""
ACTIVATING=0
OVERRIDE="/etc/systemd/system/$SERVICE.service.d/90-canonical-root.conf"

cleanup() {
  local status=$?
  if (( status != 0 && ACTIVATING == 1 )); then
    cp -a "$backup_dir/nginx.conf" "$NGINX_TARGET"
    if [[ -f "$backup_dir/service-override.conf" ]]; then
      cp -a "$backup_dir/service-override.conf" "$OVERRIDE"
    else
      rm -f -- "$OVERRIDE"
    fi
    systemctl daemon-reload
    systemctl restart "$SERVICE" || true
    nginx -t && systemctl reload nginx
    echo "Application routing restored; committed database migrations are not reversed" >&2
  fi
  if [[ -n "$MYSQL_CNF" && -f "$MYSQL_CNF" ]]; then
    rm -f -- "$MYSQL_CNF"
  fi
  if [[ -n "$NGINX_CONFIG" && -f "$NGINX_CONFIG" ]]; then
    rm -f -- "$NGINX_CONFIG"
  fi
  exit "$status"
}
trap cleanup EXIT

test -f "$ENV_FILE" || { echo "Missing deployment environment file" >&2; exit 1; }
test -d "$APP_ROOT" || { echo "项目根目录不存在：$APP_ROOT" >&2; exit 1; }
test -d "$BACKEND_DIR" || { echo "后端目录不存在：$BACKEND_DIR" >&2; exit 1; }
test -d "$FRONTEND_DIR" || { echo "前端目录不存在：$FRONTEND_DIR" >&2; exit 1; }
test -d "$DEPLOY_DIR" || { echo "部署目录不存在：$DEPLOY_DIR" >&2; exit 1; }
test -x "$PYTHON_BIN" || { echo "未找到 $PYTHON_BIN。" >&2; exit 1; }
test -x "$VENV_PIP" || { echo "未找到 $VENV_PIP。" >&2; exit 1; }

# shellcheck disable=SC1091
source "$ENV_FILE"
test -d "$APP_ROOT/database/migrations" || exit 1
if [[ "${ADP_NGINX_MODE:-standalone}" == shared ]]; then
  NGINX_TARGET=/etc/nginx/snippets/adp-location.conf
  test -f "${ADP_NGINX_PARENT_CONFIG:?Missing shared Nginx parent}" || exit 1
  grep -Fq "include $NGINX_TARGET;" "$ADP_NGINX_PARENT_CONFIG" || exit 1
else
  NGINX_TARGET=/etc/nginx/conf.d/adp-auth.conf
fi
test -f "$NGINX_TARGET" || { echo "Missing existing Nginx configuration" >&2; exit 1; }
: "${APP_ENV:?auth.env 缺少 APP_ENV}"
: "${SESSION_COOKIE_SECURE:?auth.env 缺少 SESSION_COOKIE_SECURE}"
: "${TRUSTED_PROXY_HOPS:?auth.env 缺少 TRUSTED_PROXY_HOPS}"
: "${MYSQL_HOST:?auth.env 缺少 MYSQL_HOST}"
: "${MYSQL_PORT:?auth.env 缺少 MYSQL_PORT}"
: "${MYSQL_DATABASE:?auth.env 缺少 MYSQL_DATABASE}"
: "${MYSQL_USER:?auth.env 缺少 MYSQL_USER}"
: "${MYSQL_PASSWORD:?auth.env 缺少 MYSQL_PASSWORD}"
: "${ADP_SERVER_NAME:?auth.env 缺少 ADP_SERVER_NAME}"
: "${ADP_TLS_CERTIFICATE:?auth.env 缺少 ADP_TLS_CERTIFICATE}"
: "${ADP_TLS_CERTIFICATE_KEY:?auth.env 缺少 ADP_TLS_CERTIFICATE_KEY}"

[[ "${APP_ENV,,}" == "production" ]] || { echo "deploy.sh 仅允许 APP_ENV=production。" >&2; exit 1; }
[[ "${SESSION_COOKIE_SECURE,,}" == "true" ]] || { echo "生产发布必须设置 SESSION_COOKIE_SECURE=true。" >&2; exit 1; }
[[ "${TRUSTED_PROXY_HOPS:-}" == "1" ]] || { echo "当前单层 Nginx 拓扑必须设置 TRUSTED_PROXY_HOPS=1。" >&2; exit 1; }
[[ "$ADP_SERVER_NAME" =~ ^[A-Za-z0-9.-]+$ ]] || { echo "ADP_SERVER_NAME 格式无效。" >&2; exit 1; }
[[ "$ADP_TLS_CERTIFICATE" =~ ^/[A-Za-z0-9._/-]+$ ]] || { echo "ADP_TLS_CERTIFICATE 必须是安全的绝对路径。" >&2; exit 1; }
[[ "$ADP_TLS_CERTIFICATE_KEY" =~ ^/[A-Za-z0-9._/-]+$ ]] || { echo "ADP_TLS_CERTIFICATE_KEY 必须是安全的绝对路径。" >&2; exit 1; }
test -r "$ADP_TLS_CERTIFICATE" || { echo "TLS 证书不可读：$ADP_TLS_CERTIFICATE" >&2; exit 1; }
test -r "$ADP_TLS_CERTIFICATE_KEY" || { echo "TLS 私钥不可读：$ADP_TLS_CERTIFICATE_KEY" >&2; exit 1; }

if [[ -d "$APP_ROOT" ]]; then
  backup_root="/opt/adp/backups"
  backup_dir="$backup_root/$(date +%Y%m%d%H%M%S)"
  install -d -m 0750 "$backup_root" "$backup_dir"
  cp -a "$BACKEND_DIR" "$FRONTEND_DIR" "$APP_ROOT/database" "$backup_dir/"
  cp -a "$NGINX_TARGET" "$backup_dir/nginx.conf"
  cp -a "$ENV_FILE" "$backup_dir/environment"
  systemctl cat "$SERVICE" > "$backup_dir/service.txt"
  if [[ -f "$OVERRIDE" ]]; then cp -a "$OVERRIDE" "$backup_dir/service-override.conf"; fi
fi

cd "$APP_ROOT"
"$VENV_PIP" install --no-cache-dir -r "$BACKEND_DIR/requirements.txt"
ELECTRON_SKIP_BINARY_DOWNLOAD=1 npm --prefix "$FRONTEND_DIR" ci
VITE_PUBLIC_BASE_PATH="${ADP_PUBLIC_PATH:-/adp/}" npm --prefix "$FRONTEND_DIR" run build
npm --prefix "$FRONTEND_DIR" prune --omit=dev

mysql_client() {
  local executable="$1"
  shift
  MYSQL_PWD="$MYSQL_PASSWORD" "$executable" --no-defaults --protocol=tcp \
    --host="$MYSQL_HOST" --port="$MYSQL_PORT" --user="$MYSQL_USER" "$@"
}
grants="$(mysql_client mysql --batch --skip-column-names --execute="SHOW GRANTS")"
while IFS= read -r grant; do
  [[ -z "$grant" || "$grant" == *"GRANT USAGE ON *.*"* ]] && continue
  [[ "$grant" == *" ON \`$MYSQL_DATABASE\`.* TO "* ]] || {
    echo "database grants are not isolated to $MYSQL_DATABASE" >&2
    exit 1
  }
done <<< "$grants"
mysql_client mysqldump --single-transaction --routines --triggers "$MYSQL_DATABASE" > "$backup_dir/database.sql"
migration_registry="database/migrations/000_schema_migrations.sql"
mysql_client mysql --database="$MYSQL_DATABASE" < "$migration_registry"

shopt -s nullglob
migrations=(database/migrations/[0-9][0-9][0-9]_*.sql)
for migration in "${migrations[@]}"; do
  if [[ "$migration" == "$migration_registry" ]]; then
    continue
  fi

  version="$(basename "$migration" .sql)"
  if [[ ! "$version" =~ ^[0-9]{3}_[a-z0-9_]+$ ]]; then
    echo "非法迁移文件名：$migration" >&2
    exit 1
  fi
  checksum="$(sed 's/\r$//' "$migration" | sha256sum | awk '{print $1}')"
  crlf_checksum="$(sed 's/\r$//' "$migration" | sed 's/$/\r/' | sha256sum | awk '{print $1}')"
  recorded_checksum="$(mysql_client mysql --database="$MYSQL_DATABASE" --batch --skip-column-names --execute="SELECT checksum FROM schema_migrations WHERE version = '$version' LIMIT 1")"

  if [[ -n "$recorded_checksum" ]]; then
    if [[ "$recorded_checksum" != "$checksum" && "$recorded_checksum" != "$crlf_checksum" ]]; then
      echo "迁移校验和不一致，拒绝发布：$version" >&2
      exit 1
    fi
    echo "已应用迁移：$version"
    continue
  fi

  echo "正在应用迁移：$version"
  mysql_client mysql --database="$MYSQL_DATABASE" < "$migration"
  mysql_client mysql --database="$MYSQL_DATABASE" --execute="INSERT INTO schema_migrations (version, checksum) VALUES ('$version', '$checksum')"
done
mysql_client mysql --database="$MYSQL_DATABASE" < database/seed_reference.sql

chown -R adp:adp "$APP_ROOT"
chmod 0755 "$APP_ROOT" "$BACKEND_DIR" "$FRONTEND_DIR"
# Only the public build is readable by the Nginx worker; backups/env stay private.
find "$FRONTEND_DIR/dist" -type d -exec chmod 0755 {} +
find "$FRONTEND_DIR/dist" -type f -exec chmod 0644 {} +
if [[ "${AGENT_SIDECAR_HOME:-}" == /var/lib/adp/agent-sidecar ]]; then
  install -d -o adp -g adp -m 0700 "$AGENT_SIDECAR_HOME/sessions"
  chown -R adp:adp "$AGENT_SIDECAR_HOME/sessions"
fi
NGINX_CONFIG="$(mktemp /etc/adp/nginx-adp.XXXXXX)"
install -d -o root -g root -m 0755 /var/lib/adp-acme
sed \
  -e "s|__ADP_SERVER_NAME__|$ADP_SERVER_NAME|g" \
  -e "s|__ADP_TLS_CERTIFICATE__|$ADP_TLS_CERTIFICATE|g" \
  -e "s|__ADP_TLS_CERTIFICATE_KEY__|$ADP_TLS_CERTIFICATE_KEY|g" \
  "$DEPLOY_DIR/nginx-adp.conf" > "$NGINX_CONFIG"
if grep -q '__ADP_' "$NGINX_CONFIG"; then
  echo "Nginx TLS 配置仍有未替换变量，拒绝发布。" >&2
  exit 1
fi
if [[ "${ADP_NGINX_MODE:-standalone}" == shared ]]; then
  ADP_SERVER_NAME="$ADP_SERVER_NAME" ADP_PUBLIC_PATH="${ADP_PUBLIC_PATH:-/adp/}" \
    bash "$DEPLOY_DIR/render-shared-location.sh" "$APP_ROOT" "$BACKEND_PORT" > "$NGINX_CONFIG"
fi
ACTIVATING=1
install -o root -g root -m 0644 "$NGINX_CONFIG" "$NGINX_TARGET"
nginx -t
install -d -m 0755 "$(dirname "$OVERRIDE")"
printf '[Service]\nWorkingDirectory=%s\nExecStart=\nExecStart=%s --workers 2 --threads 2 --bind 127.0.0.1:%s --access-logfile - --error-logfile - backend.app:app\n' \
  "$APP_ROOT" "$(dirname "$VENV_PIP")/gunicorn" "$BACKEND_PORT" > "$OVERRIDE"
systemctl daemon-reload
systemctl restart "$SERVICE"
systemctl reload nginx
for attempt in $(seq 1 30); do
  if curl --fail --silent -H "Host: $ADP_SERVER_NAME" "http://127.0.0.1:$BACKEND_PORT/api/v1/health" >/dev/null 2>&1; then
    break
  fi
  if [[ "$attempt" == "30" ]]; then
    echo "Flask 健康检查超时，请查看 journalctl -u adp-auth。" >&2
    exit 1
  fi
  sleep 1
done
curl --fail --silent --show-error --resolve "$ADP_SERVER_NAME:443:127.0.0.1" "https://${ADP_SERVER_NAME}${ADP_PUBLIC_PATH:-/adp/}healthz" >/dev/null
curl --fail --silent --show-error "https://${ADP_SERVER_NAME}${ADP_PUBLIC_PATH:-/adp/}api/v1/health" >/dev/null
ACTIVATING=0
echo "ADP 登录注册服务发布完成。"
