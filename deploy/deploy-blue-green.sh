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

env_value() {
  local key="$1" line value
  line="$(grep -m1 -E "^${key}=" "$LIVE_ENV")" || { echo "missing $key" >&2; return 1; }
  value="${line#*=}"
  if [[ "$value" == \"*\" && "$value" == *\" ]]; then value="${value:1:${#value}-2}"; fi
  if [[ "$value" == \'*\' && "$value" == *\' ]]; then value="${value:1:${#value}-2}"; fi
  printf '%s' "$value"
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

grant_database() {
  local database="$1" host
  while IFS= read -r host; do
    [[ "$host" =~ ^[A-Za-z0-9.%:_-]+$ ]] || { echo "unsafe MySQL host" >&2; exit 1; }
    mysql --execute="GRANT ALL PRIVILEGES ON \`${database}\`.* TO '${MYSQL_USER}'@'${host}'"
  done < <(mysql --batch --skip-column-names --execute="SELECT Host FROM mysql.user WHERE User='${MYSQL_USER}'")
}

clone_database() {
  local destination="$1"
  mysql --execute="CREATE DATABASE \`${destination}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
  mysqldump --single-transaction --routines --triggers --events "$MYSQL_DATABASE" | mysql "$destination"
  grant_database "$destination"
}

migrate_database() {
  local database="$1" migration version checksum legacy_crlf_checksum recorded
  mysql "$database" < database/migrations/000_schema_migrations.sql
  for migration in database/migrations/[0-9][0-9][0-9]_*.sql; do
    [[ "$migration" == *000_schema_migrations.sql ]] && continue
    version="$(basename "$migration" .sql)"
    checksum="$(sha256sum "$migration" | awk '{print $1}')"
    legacy_crlf_checksum="$(sed 's/\r$//' "$migration" | sed 's/$/\r/' | sha256sum | awk '{print $1}')"
    recorded="$(mysql "$database" --batch --skip-column-names --execute="SELECT checksum FROM schema_migrations WHERE version='${version}'")"
    if [[ -n "$recorded" ]]; then
      [[ "$recorded" == "$checksum" || "$recorded" == "$legacy_crlf_checksum" ]] || {
        echo "migration checksum mismatch: $version" >&2
        exit 1
      }
      continue
    fi
    mysql "$database" < "$migration"
    mysql "$database" --execute="INSERT INTO schema_migrations(version,checksum) VALUES ('${version}','${checksum}')"
  done
  mysql "$database" < database/seed_reference.sql
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
  cp -a "$NGINX_LIVE" "$STATE_DIR/previous-nginx.conf"
  tar -C "$(dirname "$LIVE_APP")" -czf "$BACKUP_DIR/live-code.tgz" "$(basename "$LIVE_APP")"
  mysqldump --single-transaction --routines --triggers --events "$MYSQL_DATABASE" > "$BACKUP_DIR/live-database.sql"
  if [[ -d /var/lib/adp/attachments ]]; then
    tar -C /var/lib/adp -czf "$BACKUP_DIR/attachments.tgz" attachments
  fi
  sha256sum "$BACKUP_DIR"/* > "$BACKUP_DIR/SHA256SUMS"
}

render_nginx() {
  sed -e "s|__ADP_SERVER_NAME__|$SERVER_NAME|g" \
    -e "s|__ADP_TLS_CERTIFICATE__|$TLS_CERT|g" \
    -e "s|__ADP_TLS_CERTIFICATE_KEY__|$TLS_KEY|g" \
    -e "s|__ADP_RELEASE_PATH__|$RELEASE_DIR|g" \
    -e 's|__ADP_BACKEND_PORT__|5002|g' \
    deploy/nginx-adp-blue-green.conf > "$STATE_DIR/new-nginx.conf"
  ! grep -q '__ADP_' "$STATE_DIR/new-nginx.conf"
}

install_nginx_config() {
  local source="$1" temporary=/etc/nginx/conf.d/.adp-auth.conf.next
  install -o root -g root -m 0644 "$source" "$temporary"
  mv -f -- "$temporary" "$NGINX_LIVE"
  if ! nginx -t; then
    return 1
  fi
  systemctl reload nginx
}

restore_previous() {
  local temporary=/etc/nginx/conf.d/.adp-auth.conf.restore
  install -o root -g root -m 0644 "$STATE_DIR/previous-nginx.conf" "$temporary"
  mv -f -- "$temporary" "$NGINX_LIVE"
  nginx -t
  systemctl reload nginx
}

verify_public() {
  curl --fail --silent --show-error --resolve "$SERVER_NAME:443:127.0.0.1" "https://$SERVER_NAME/healthz" >/dev/null
  curl --fail --silent --show-error --resolve "$SERVER_NAME:443:127.0.0.1" "https://$SERVER_NAME/api/v1/health" >/dev/null
  curl --fail --silent --show-error --resolve "$SERVER_NAME:443:127.0.0.1" "https://$SERVER_NAME/workbench" >/dev/null
  curl --fail --silent --show-error --resolve "$SERVER_NAME:443:127.0.0.1" "https://$SERVER_NAME/api-docs/" >/dev/null
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
  activate_release "$2"
  exit 0
fi

[[ $# == 3 ]] || { echo "usage: $0 ARCHIVE SHA256 RELEASE_ID" >&2; exit 2; }
ARCHIVE="$1"; EXPECTED_SHA="$2"; RELEASE_ID="$3"
[[ "$RELEASE_ID" =~ ^[A-Za-z0-9._-]+$ ]] || { echo "invalid release id" >&2; exit 2; }
[[ "$EXPECTED_SHA" =~ ^[a-f0-9]{64}$ ]] || { echo "invalid SHA-256" >&2; exit 2; }
[[ -f "$ARCHIVE" && -f "$LIVE_ENV" && -f "$NGINX_LIVE" ]] || { echo "missing deployment input" >&2; exit 1; }
[[ -f /usr/include/jpeglib.h && -f /usr/include/freetype2/ft2build.h ]] || {
  echo "missing Pillow build headers: install libjpeg-turbo-devel and freetype-devel" >&2
  exit 1
}
ACTUAL_SHA="$(sha256sum "$ARCHIVE" | awk '{print $1}')"
[[ "$ACTUAL_SHA" == "$EXPECTED_SHA" ]] || { echo "release checksum mismatch" >&2; exit 1; }

RELEASE_DIR="$RELEASE_ROOT/$RELEASE_ID"
STATE_DIR="$STATE_ROOT/$RELEASE_ID"
BACKUP_DIR="/opt/adp/backups/${RELEASE_ID}-blue-green"
DB_SUFFIX="${RELEASE_ID//[^A-Za-z0-9]/_}"
ACCEPTANCE_DB="adp_acceptance_${DB_SUFFIX}"
PRODUCTION_DB="adp_production_${DB_SUFFIX}"
MYSQL_HOST="$(env_value MYSQL_HOST)"; MYSQL_PORT="$(env_value MYSQL_PORT)"
MYSQL_USER="$(env_value MYSQL_USER)"; MYSQL_PASSWORD="$(env_value MYSQL_PASSWORD)"
MYSQL_DATABASE="$(env_value MYSQL_DATABASE)"; SERVER_NAME="$(env_value ADP_SERVER_NAME)"
TLS_CERT="$(env_value ADP_TLS_CERTIFICATE)"; TLS_KEY="$(env_value ADP_TLS_CERTIFICATE_KEY)"
[[ "$MYSQL_USER" =~ ^[A-Za-z0-9_]+$ && "$MYSQL_DATABASE" =~ ^[A-Za-z0-9_]+$ ]] || { echo "unsafe database identity" >&2; exit 1; }
[[ ! -e "$RELEASE_DIR" && ! -e "$STATE_DIR" ]] || { echo "release already exists" >&2; exit 1; }

install -d -o root -g root -m 0711 "$RELEASE_ROOT" "$SLOT_ROOT"
install -d -o root -g root -m 0750 "$STATE_DIR"
install -d -m 0755 "$RELEASE_DIR"
tar -xzf "$ARCHIVE" -C "$RELEASE_DIR"
cd "$RELEASE_DIR"
"/opt/adp-venv/bin/python" -m venv .venv
PIP_DISABLE_PIP_VERSION_CHECK=1 .venv/bin/pip install --no-cache-dir -r backend/requirements.txt
npm --prefix frontend ci
npm --prefix frontend audit --audit-level=low
npm --prefix frontend run build
chmod -R u=rwX,go=rX frontend/dist api-docs

# Deployment sequence
backup_live
clone_database "$ACCEPTANCE_DB"
migrate_database "$ACCEPTANCE_DB"
reconcile_database "$ACCEPTANCE_DB"
write_env "$ACCEPTANCE_DB" "$NEXT_ENV"
ln -sfn "$RELEASE_DIR" "$SLOT_ROOT/green.next"
mv -Tf "$SLOT_ROOT/green.next" "$SLOT_ROOT/green"
install -o root -g root -m 0644 deploy/adp-next.service /etc/systemd/system/adp-next.service
chown -R adp:adp "$RELEASE_DIR"
systemctl daemon-reload
systemctl enable adp-next
systemctl restart adp-next
for _ in $(seq 1 30); do curl --fail --silent http://127.0.0.1:5002/api/v1/health >/dev/null && break; sleep 1; done
curl --fail --silent --show-error http://127.0.0.1:5002/api/v1/health >/dev/null
for _ in $(seq 1 50); do curl --fail --silent http://127.0.0.1:5002/api/v1/health >/dev/null; done

clone_database "$PRODUCTION_DB"
migrate_database "$PRODUCTION_DB"
reconcile_database "$PRODUCTION_DB"
write_env "$PRODUCTION_DB" "$NEXT_ENV"
systemctl restart adp-next
for _ in $(seq 1 30); do curl --fail --silent http://127.0.0.1:5002/api/v1/health >/dev/null && break; sleep 1; done
curl --fail --silent --show-error http://127.0.0.1:5002/api/v1/health >/dev/null
render_nginx
printf 'release_id=%s\nrelease_sha256=%s\nrelease_dir=%s\nacceptance_database=%s\nproduction_database=%s\nbackup_dir=%s\n' \
  "$RELEASE_ID" "$ACTUAL_SHA" "$RELEASE_DIR" "$ACCEPTANCE_DB" "$PRODUCTION_DB" "$BACKUP_DIR" > "$STATE_DIR/release.env"
activate_release "$RELEASE_ID"
echo "blue-green deployment complete: $RELEASE_ID"
