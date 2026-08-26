#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "$(id -u)" != "0" ]]; then
  echo "请使用 root 执行此脚本。" >&2
  exit 1
fi

APP_ROOT="${APP_ROOT:-/opt/adp/login-registration}"
PYTHON_BIN="${PYTHON_BIN:-/opt/adp-venv/bin/python}"
VENV_PIP="${VENV_PIP:-/opt/adp-venv/bin/pip}"
MYSQL_CNF=""
NGINX_CONFIG=""

cleanup() {
  if [[ -n "$MYSQL_CNF" && -f "$MYSQL_CNF" ]]; then
    rm -f -- "$MYSQL_CNF"
  fi
  if [[ -n "$NGINX_CONFIG" && -f "$NGINX_CONFIG" ]]; then
    rm -f -- "$NGINX_CONFIG"
  fi
}
trap cleanup EXIT

test -f /etc/adp/auth.env || { echo "缺少 /etc/adp/auth.env，拒绝发布。" >&2; exit 1; }
test -x "$PYTHON_BIN" || { echo "未找到 $PYTHON_BIN。" >&2; exit 1; }
test -x "$VENV_PIP" || { echo "未找到 $VENV_PIP。" >&2; exit 1; }

# shellcheck disable=SC1091
source /etc/adp/auth.env
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

if [[ -d "$APP_ROOT/实现文档/登陆注册" ]]; then
  backup_root="/opt/adp/backups"
  backup_dir="$backup_root/$(date +%Y%m%d%H%M%S)"
  install -d -m 0750 "$backup_root" "$backup_dir"
  cp -a "$APP_ROOT/实现文档/登陆注册" "$backup_dir/"
fi

cd "$APP_ROOT/实现文档/登陆注册"
"$VENV_PIP" install --no-cache-dir -r backend/requirements.txt
npm --prefix frontend ci
npm --prefix frontend run build
npm --prefix frontend prune --omit=dev

MYSQL_CNF="$(mktemp /etc/adp/mysql-client.XXXXXX)"
chmod 600 "$MYSQL_CNF"
{
  echo '[client]'
  echo "host=$MYSQL_HOST"
  echo "port=$MYSQL_PORT"
  echo "user=$MYSQL_USER"
  echo "password=$MYSQL_PASSWORD"
} > "$MYSQL_CNF"
migration_registry="database/migrations/000_schema_migrations.sql"
mysql --defaults-extra-file="$MYSQL_CNF" --database="$MYSQL_DATABASE" < "$migration_registry"

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
  checksum="$(sha256sum "$migration" | awk '{print $1}')"
  recorded_checksum="$(mysql --defaults-extra-file="$MYSQL_CNF" --database="$MYSQL_DATABASE" --batch --skip-column-names --execute="SELECT checksum FROM schema_migrations WHERE version = '$version' LIMIT 1")"

  if [[ -n "$recorded_checksum" ]]; then
    if [[ "$recorded_checksum" != "$checksum" ]]; then
      echo "迁移校验和不一致，拒绝发布：$version" >&2
      exit 1
    fi
    echo "已应用迁移：$version"
    continue
  fi

  echo "正在应用迁移：$version"
  mysql --defaults-extra-file="$MYSQL_CNF" --database="$MYSQL_DATABASE" < "$migration"
  mysql --defaults-extra-file="$MYSQL_CNF" --database="$MYSQL_DATABASE" --execute="INSERT INTO schema_migrations (version, checksum) VALUES ('$version', '$checksum')"
done
mysql --defaults-extra-file="$MYSQL_CNF" --database="$MYSQL_DATABASE" < database/seed_reference.sql

chown -R adp:adp "$APP_ROOT"
chmod 0755 "$APP_ROOT" "$APP_ROOT/实现文档" "$APP_ROOT/实现文档/登陆注册"
NGINX_CONFIG="$(mktemp /etc/adp/nginx-adp.XXXXXX)"
sed \
  -e "s|__ADP_SERVER_NAME__|$ADP_SERVER_NAME|g" \
  -e "s|__ADP_TLS_CERTIFICATE__|$ADP_TLS_CERTIFICATE|g" \
  -e "s|__ADP_TLS_CERTIFICATE_KEY__|$ADP_TLS_CERTIFICATE_KEY|g" \
  deploy/nginx-adp.conf > "$NGINX_CONFIG"
if grep -q '__ADP_' "$NGINX_CONFIG"; then
  echo "Nginx TLS 配置仍有未替换变量，拒绝发布。" >&2
  exit 1
fi
install -o root -g root -m 0644 "$NGINX_CONFIG" /etc/nginx/conf.d/adp-auth.conf
nginx -t
systemctl daemon-reload
systemctl restart adp-auth
systemctl reload nginx
for attempt in $(seq 1 30); do
  if curl --fail --silent http://127.0.0.1:5001/api/v1/health >/dev/null 2>&1; then
    break
  fi
  if [[ "$attempt" == "30" ]]; then
    echo "Flask 健康检查超时，请查看 journalctl -u adp-auth。" >&2
    exit 1
  fi
  sleep 1
done
curl --fail --silent --show-error --resolve "$ADP_SERVER_NAME:443:127.0.0.1" "https://$ADP_SERVER_NAME/healthz" >/dev/null
echo "ADP 登录注册服务发布完成。"
