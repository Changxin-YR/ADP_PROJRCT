#!/usr/bin/env bash
set -Eeuo pipefail
umask 027

[[ "$(id -u)" == "0" ]] || { echo "run as root" >&2; exit 1; }
exec 9>/run/lock/adp-blue-green.lock
flock -n 9 || { echo "another ADP deployment is running" >&2; exit 1; }

LIVE_ENV=/etc/adp/auth.env
NEXT_ENV=/etc/adp/next.env
NGINX_LIVE=/etc/nginx/conf.d/adp-auth.conf
RELEASE_ROOT=/opt/adp/releases
SLOT_ROOT=/opt/adp/slots
STATE_ROOT=/var/lib/adp/deployments
LIVE_APP=/opt/adp/login-registration/实现文档/登陆注册
SHARED_NGINX_INCLUDE=/etc/nginx/snippets/adp-location.conf
NGINX_MODE=standalone
PUBLIC_PATH=/adp/
PUBLIC_PREFIX=/adp

env_value() {
  local key="$1" line value
  line="$(grep -m1 -E "^${key}=" "$LIVE_ENV")" || { echo "missing $key" >&2; return 1; }
  value="${line#*=}"
  if [[ "$value" == \"*\" && "$value" == *\" ]]; then value="${value:1:${#value}-2}"; fi
  if [[ "$value" == \'*\' && "$value" == *\' ]]; then value="${value:1:${#value}-2}"; fi
  printf '%s' "$value"
}

load_nginx_mode() {
  NGINX_MODE="$(env_value ADP_NGINX_MODE 2>/dev/null || printf 'standalone')"
  [[ "$NGINX_MODE" == "shared" || "$NGINX_MODE" == "standalone" ]] || { echo "invalid ADP_NGINX_MODE" >&2; exit 1; }
  if [[ "$NGINX_MODE" == "shared" ]]; then
    PARENT_NGINX_CONFIG="$(env_value ADP_NGINX_PARENT_CONFIG 2>/dev/null || true)"
    [[ -n "$PARENT_NGINX_CONFIG" && -f "$PARENT_NGINX_CONFIG" ]] || { echo "shared mode requires ADP_NGINX_PARENT_CONFIG" >&2; exit 1; }
    grep -Fq "include $SHARED_NGINX_INCLUDE;" "$PARENT_NGINX_CONFIG" || {
      echo "shared mode requires $PARENT_NGINX_CONFIG to include $SHARED_NGINX_INCLUDE" >&2
      exit 1
    }
    [[ -f "$SHARED_NGINX_INCLUDE" ]] || { echo "missing existing shared Nginx include" >&2; exit 1; }
  fi
}

load_public_path() {
  PUBLIC_PATH="$(env_value ADP_PUBLIC_PATH 2>/dev/null || printf '/adp/')"
  [[ "$PUBLIC_PATH" =~ ^/[A-Za-z0-9._~-]+/$ ]] || { echo "invalid ADP_PUBLIC_PATH" >&2; exit 1; }
  PUBLIC_PREFIX="${PUBLIC_PATH%/}"
}

mysql_cmd() {
  MYSQL_PWD="$MYSQL_PASSWORD" mysql --no-defaults --protocol=tcp \
    --host="$MYSQL_HOST" --port="$MYSQL_PORT" --user="$MYSQL_USER" "$@"
}

assert_database_isolated() {
  local database="$1" grant grants
  grants="$(mysql_cmd --batch --skip-column-names --execute="SHOW GRANTS")"
  while IFS= read -r grant; do
    [[ -z "$grant" || "$grant" == *"GRANT USAGE ON *.*"* ]] && continue
    [[ "$grant" == *" ON \`$database\`.* TO "* ]] || {
      echo "database grants are not isolated to $database" >&2
      return 1
    }
  done <<<"$grants"
}

write_env() {
  local database="$1" destination="$2" temporary
  temporary="$(mktemp /etc/adp/next.env.XXXXXX)"
  awk -v database="$database" '
    BEGIN { replaced=0 }
    /^MYSQL_DATABASE=/ { print "MYSQL_DATABASE=" database; replaced=1; next }
    { print }
    END { if (!replaced) print "MYSQL_DATABASE=" database }
  ' "$LIVE_ENV" > "$temporary"
  install -o root -g root -m 0600 "$temporary" "$destination"
  rm -f -- "$temporary"
}

migrate_database() {
  local database="$1" migration version checksum legacy_crlf_checksum recorded
  mysql_cmd "$database" < database/migrations/000_schema_migrations.sql
  for migration in database/migrations/[0-9][0-9][0-9]_*.sql; do
    [[ "$migration" == *000_schema_migrations.sql ]] && continue
    version="$(basename "$migration" .sql)"
    # Treat line-ending changes as equivalent; old hosts may have registered LF checksums
    # while the release archive preserves CRLF blobs from the repository.
    checksum="$(sed 's/\r$//' "$migration" | sha256sum | awk '{print $1}')"
    legacy_crlf_checksum="$(sed 's/\r$//' "$migration" | sed 's/$/\r/' | sha256sum | awk '{print $1}')"
    recorded="$(mysql_cmd "$database" --batch --skip-column-names --execute="SELECT checksum FROM schema_migrations WHERE version='${version}'")"
    if [[ -n "$recorded" ]]; then
      [[ "$recorded" == "$checksum" || "$recorded" == "$legacy_crlf_checksum" ]] || {
        echo "migration checksum mismatch: $version" >&2
        exit 1
      }
      continue
    fi
    mysql_cmd "$database" < "$migration"
    mysql_cmd "$database" --execute="INSERT INTO schema_migrations(version,checksum) VALUES ('${version}','${checksum}')"
  done
  mysql_cmd "$database" < database/seed_reference.sql
}

reconcile_database() {
  local database="$1"
  local output="$STATE_DIR/${database}-reconciliation.json"
  env MYSQL_HOST="$MYSQL_HOST" MYSQL_PORT="$MYSQL_PORT" MYSQL_USER="$MYSQL_USER" \
    MYSQL_PASSWORD="$MYSQL_PASSWORD" MYSQL_DATABASE="$database" \
    "$RELEASE_DIR/.venv/bin/python" backend/scripts/reconcile_enterprise_data.py \
      --database "$database" --output "$output"
}

backup_live() {
  install -d -m 0750 "$BACKUP_DIR"
  if [[ "$NGINX_MODE" == "shared" ]]; then
    cp -a "$SHARED_NGINX_INCLUDE" "$STATE_DIR/previous-nginx.conf"
  else
    cp -a "$NGINX_LIVE" "$STATE_DIR/previous-nginx.conf"
  fi
  tar -C "$(dirname "$LIVE_APP")" -czf "$BACKUP_DIR/live-code.tgz" "$(basename "$LIVE_APP")"
  mysqldump --single-transaction --routines --triggers --events "$MYSQL_DATABASE" > "$BACKUP_DIR/live-database.sql"
  if [[ -d /var/lib/adp/attachments ]]; then
    tar -C /var/lib/adp -czf "$BACKUP_DIR/attachments.tgz" attachments
  fi
  sha256sum "$BACKUP_DIR"/* > "$BACKUP_DIR/SHA256SUMS"
}

render_nginx() {
  local template=deploy/nginx-adp-blue-green.conf
  [[ "$NGINX_MODE" == "shared" ]] && template=deploy/nginx-adp-shared-location.conf
  sed -e "s|__ADP_SERVER_NAME__|$SERVER_NAME|g" \
    -e "s|__ADP_TLS_CERTIFICATE__|$TLS_CERT|g" \
    -e "s|__ADP_TLS_CERTIFICATE_KEY__|$TLS_KEY|g" \
    -e "s|__ADP_RELEASE_PATH__|$RELEASE_DIR|g" \
    -e 's|__ADP_BACKEND_PORT__|5002|g' \
    -e "s|__ADP_PUBLIC_PATH__|$PUBLIC_PATH|g" \
    -e "s|__ADP_PUBLIC_PREFIX__|$PUBLIC_PREFIX|g" \
    "$template" > "$STATE_DIR/new-nginx.conf"
  ! grep -q '__ADP_' "$STATE_DIR/new-nginx.conf"
}

install_nginx_config() {
  local source="$1" temporary=/etc/nginx/conf.d/.adp-auth.conf.next
  if [[ "$NGINX_MODE" == "shared" ]]; then
    install -o root -g root -m 0644 "$source" "$SHARED_NGINX_INCLUDE"
    nginx -t
    systemctl reload nginx
    return
  fi
  install -o root -g root -m 0644 "$source" "$temporary"
  mv -f -- "$temporary" "$NGINX_LIVE"
  if ! nginx -t; then
    return 1
  fi
  systemctl reload nginx
}

restore_previous() {
  if [[ "$NGINX_MODE" == "shared" ]]; then
    install -o root -g root -m 0644 "$STATE_DIR/previous-nginx.conf" "$SHARED_NGINX_INCLUDE"
    nginx -t
    systemctl reload nginx
    return
  fi
  local temporary=/etc/nginx/conf.d/.adp-auth.conf.restore
  install -o root -g root -m 0644 "$STATE_DIR/previous-nginx.conf" "$temporary"
  mv -f -- "$temporary" "$NGINX_LIVE"
  nginx -t
  systemctl reload nginx
}

cleanup_on_error() {
  local status=$?
  if (( status != 0 )); then
    if [[ -n "${STATE_DIR:-}" && -f "${STATE_DIR}/previous-nginx.conf" ]]; then
      restore_previous || true
    fi
    if [[ -n "${PREVIOUS_RELEASE:-}" && -d "$PREVIOUS_RELEASE" ]]; then
      current_release="$(readlink -f "$SLOT_ROOT/green" 2>/dev/null || true)"
      if [[ "$current_release" != "$PREVIOUS_RELEASE" ]]; then
        ln -sfn "$PREVIOUS_RELEASE" "$SLOT_ROOT/green.rollback"
        mv -Tf "$SLOT_ROOT/green.rollback" "$SLOT_ROOT/green"
      fi
    fi
    if [[ "${MIGRATION_IN_PROGRESS:-0}" != "1" && "${NEXT_SERVICE_WAS_ACTIVE:-0}" == "1" ]]; then
      systemctl start adp-next || true
    fi
    if [[ "${MIGRATION_IN_PROGRESS:-0}" != "1" && "${OLD_SERVICE_WAS_ACTIVE:-0}" == "1" ]]; then
      systemctl start adp-auth || true
    fi
    if [[ "${MIGRATION_IN_PROGRESS:-0}" != "1" && -n "${MAINTENANCE_MARKER:-}" ]]; then
      rm -f -- "$MAINTENANCE_MARKER"
    elif [[ "${MIGRATION_IN_PROGRESS:-0}" == "1" ]]; then
      echo "database migration failed; services remain stopped and maintenance marker is preserved" >&2
    fi
  fi
  exit "$status"
}
trap cleanup_on_error EXIT

verify_public() {
  local base="${ADP_PUBLIC_BASE_URL:-https://$SERVER_NAME$PUBLIC_PREFIX}"
  [[ "$base" == "https://$SERVER_NAME" || "$base" == "https://$SERVER_NAME$PUBLIC_PREFIX" ]] || {
    echo "ADP_PUBLIC_BASE_URL must match the configured production host or public path" >&2
    return 1
  }
  curl --fail --silent --show-error "$base/healthz" >/dev/null
  curl --fail --silent --show-error "$base/api/v1/health" >/dev/null
  curl --fail --silent --show-error "$base/workbench" >/dev/null
  curl --fail --silent --show-error "$base/api-docs/" >/dev/null
}

activate_release() {
  local release_id="$1"
  STATE_DIR="$STATE_ROOT/$release_id"
  [[ -f "$STATE_DIR/new-nginx.conf" ]] || { echo "unknown release: $release_id" >&2; exit 1; }
  SERVER_NAME="$(env_value ADP_SERVER_NAME)"
  if ! install_nginx_config "$STATE_DIR/new-nginx.conf" || ! verify_public; then
    restore_previous
    return 1
  fi
  date --iso-8601=seconds > "$STATE_DIR/activated-at"
}

if [[ "${1:-}" == "--activate" ]]; then
  [[ $# == 2 ]] || { echo "usage: $0 --activate RELEASE_ID" >&2; exit 2; }
  SERVER_NAME="$(env_value ADP_SERVER_NAME)"
  load_public_path
  load_nginx_mode
  activate_release "$2"
  exit 0
fi

[[ $# == 3 ]] || { echo "usage: $0 ARCHIVE SHA256 RELEASE_ID" >&2; exit 2; }
ARCHIVE="$1"; EXPECTED_SHA="$2"; RELEASE_ID="$3"
[[ "$RELEASE_ID" =~ ^[A-Za-z0-9._-]+$ ]] || { echo "invalid release id" >&2; exit 2; }
[[ "$EXPECTED_SHA" =~ ^[a-f0-9]{64}$ ]] || { echo "invalid SHA-256" >&2; exit 2; }
[[ -f "$ARCHIVE" && -f "$LIVE_ENV" ]] || { echo "missing deployment input" >&2; exit 1; }
[[ -f /usr/include/jpeglib.h && -f /usr/include/freetype2/ft2build.h ]] || {
  echo "missing Pillow build headers: install libjpeg-turbo-devel and freetype-devel" >&2
  exit 1
}
ACTUAL_SHA="$(sha256sum "$ARCHIVE" | awk '{print $1}')"
[[ "$ACTUAL_SHA" == "$EXPECTED_SHA" ]] || { echo "release checksum mismatch" >&2; exit 1; }

RELEASE_DIR="$RELEASE_ROOT/$RELEASE_ID"
STATE_DIR="$STATE_ROOT/$RELEASE_ID"
BACKUP_DIR="/opt/adp/backups/${RELEASE_ID}-blue-green"
MYSQL_HOST="$(env_value MYSQL_HOST)"; MYSQL_PORT="$(env_value MYSQL_PORT)"
MYSQL_USER="$(env_value MYSQL_USER)"; MYSQL_PASSWORD="$(env_value MYSQL_PASSWORD)"
MYSQL_DATABASE="$(env_value MYSQL_DATABASE)"; SERVER_NAME="$(env_value ADP_SERVER_NAME)"
TLS_CERT="$(env_value ADP_TLS_CERTIFICATE)"; TLS_KEY="$(env_value ADP_TLS_CERTIFICATE_KEY)"
load_public_path
load_nginx_mode
[[ "$NGINX_MODE" == "shared" || -f "$NGINX_LIVE" ]] || { echo "standalone mode requires $NGINX_LIVE" >&2; exit 1; }
[[ "$MYSQL_USER" =~ ^[A-Za-z0-9_]+$ && "$MYSQL_DATABASE" =~ ^[A-Za-z0-9_]+$ ]] || { echo "unsafe database identity" >&2; exit 1; }
assert_database_isolated "$MYSQL_DATABASE"
[[ ! -e "$RELEASE_DIR" && ! -e "$STATE_DIR" ]] || { echo "release already exists" >&2; exit 1; }

install -d -o root -g root -m 0711 "$RELEASE_ROOT" "$SLOT_ROOT"
install -d -o root -g root -m 0750 "$STATE_DIR"
install -d -m 0755 "$RELEASE_DIR"
install -d -o root -g root -m 0755 /var/lib/adp-acme
tar -xzf "$ARCHIVE" -C "$RELEASE_DIR"
cd "$RELEASE_DIR"
require_release_files() {
  local missing=() path
  for path in backend/requirements.txt backend/app.py backend/scripts/reconcile_enterprise_data.py \
    frontend/package.json database/migrations deploy/adp-next.service api-docs/openapi.json; do
    [[ -e "$path" ]] || missing+=("$path")
  done
  ((${#missing[@]} == 0)) || { echo "release archive is missing: ${missing[*]}" >&2; return 1; }
}
require_release_files
"/opt/adp-venv/bin/python" -m venv .venv
PIP_DISABLE_PIP_VERSION_CHECK=1 .venv/bin/pip install --no-cache-dir -r backend/requirements.txt
ELECTRON_SKIP_BINARY_DOWNLOAD=1 npm --prefix frontend ci
npm --prefix frontend audit --audit-level=low --omit=dev
VITE_PUBLIC_BASE_PATH="${ADP_PUBLIC_PATH:-/adp/}" npm --prefix frontend run build
chmod -R u=rwX,go=rX frontend/dist api-docs
chmod 0755 "$RELEASE_DIR" "$RELEASE_DIR/frontend" "$RELEASE_DIR/frontend/dist" "$RELEASE_DIR/api-docs"

# Deployment sequence
backup_live
# ponytail: a short maintenance window prevents writes while the shared production schema is migrated.
MAINTENANCE_MARKER="$STATE_DIR/maintenance"
PREVIOUS_RELEASE="$(readlink -f "$SLOT_ROOT/green" 2>/dev/null || true)"
if [[ -n "$PREVIOUS_RELEASE" ]]; then printf '%s\n' "$PREVIOUS_RELEASE" > "$STATE_DIR/previous-release"; fi
OLD_SERVICE_WAS_ACTIVE=0
NEXT_SERVICE_WAS_ACTIVE=0
MIGRATION_IN_PROGRESS=0
if systemctl is-active --quiet adp-auth; then OLD_SERVICE_WAS_ACTIVE=1; fi
if systemctl is-active --quiet adp-next; then NEXT_SERVICE_WAS_ACTIVE=1; fi
systemctl stop adp-auth
systemctl stop adp-next
date --iso-8601=seconds > "$MAINTENANCE_MARKER"
MIGRATION_IN_PROGRESS=1
migrate_database "$MYSQL_DATABASE"
reconcile_database "$MYSQL_DATABASE"
MIGRATION_IN_PROGRESS=0
write_env "$MYSQL_DATABASE" "$NEXT_ENV"
ln -sfn "$RELEASE_DIR" "$SLOT_ROOT/green.next"
mv -Tf "$SLOT_ROOT/green.next" "$SLOT_ROOT/green"
install -o root -g root -m 0644 deploy/adp-next.service /etc/systemd/system/adp-next.service
chown -R adp:adp "$RELEASE_DIR"
systemctl daemon-reload
systemctl enable adp-next
systemctl restart adp-next
for _ in $(seq 1 30); do curl --fail --silent -H "Host: $SERVER_NAME" http://127.0.0.1:5002/api/v1/health >/dev/null && break; sleep 1; done
curl --fail --silent --show-error -H "Host: $SERVER_NAME" http://127.0.0.1:5002/api/v1/health >/dev/null
for _ in $(seq 1 50); do curl --fail --silent -H "Host: $SERVER_NAME" http://127.0.0.1:5002/api/v1/health >/dev/null; done
if (( OLD_SERVICE_WAS_ACTIVE )); then systemctl start adp-auth; fi
rm -f -- "$MAINTENANCE_MARKER"
render_nginx
printf 'release_id=%s\nrelease_sha256=%s\nrelease_dir=%s\ndatabase=%s\nbackup_dir=%s\n' \
  "$RELEASE_ID" "$ACTUAL_SHA" "$RELEASE_DIR" "$MYSQL_DATABASE" "$BACKUP_DIR" > "$STATE_DIR/release.env"
activate_release "$RELEASE_ID"
echo "blue-green deployment complete: $RELEASE_ID"
