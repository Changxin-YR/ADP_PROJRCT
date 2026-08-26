#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

[[ "$(id -u)" == "0" ]] || { echo "run as root" >&2; exit 1; }
exec 9>/run/lock/adp-blue-green.lock
flock -n 9 || { echo "another ADP manual test operation is running" >&2; exit 1; }

EXPECTED_DATABASE=adp_manual_test_20260817
DATABASE="${1:-}"
[[ $# == 1 && "$DATABASE" == "$EXPECTED_DATABASE" ]] || {
  echo "usage: $0 adp_manual_test_20260817" >&2; exit 2;
}

LIVE_ENV=/etc/adp/next.env
TEST_ENV=/etc/adp/manual-test.env
CREDENTIALS=/etc/adp/manual-test-credentials.env
NGINX_LIVE=/etc/nginx/conf.d/adp-auth.conf
TEST_ROOT=/var/lib/adp/manual-test-20260817
ATTACHMENTS="$TEST_ROOT/attachments"
PREVIOUS_NGINX="$TEST_ROOT/previous-nginx.conf"
TEST_DB_USER=adp_manual_test_20260817
APP_ROOT="$(pwd -P)"
PRODUCTION_ROOT=/opt/adp/slots/green
RUNTIME_ROOT="$(readlink -f "$PRODUCTION_ROOT")"

[[ -f "$LIVE_ENV" && -f "$NGINX_LIVE" && -d "$APP_ROOT" && -x "$RUNTIME_ROOT/.venv/bin/python" ]] || {
  echo "production deployment inputs are missing" >&2; exit 1;
}

env_value() {
  local key="$1" line value
  line="$(grep -m1 -E "^${key}=" "$LIVE_ENV")" || { echo "missing $key" >&2; return 1; }
  value="${line#*=}"
  if [[ "$value" == \"*\" && "$value" == *\" ]]; then value="${value:1:${#value}-2}"; fi
  if [[ "$value" == \'*\' && "$value" == *\' ]]; then value="${value:1:${#value}-2}"; fi
  printf '%s' "$value"
}

production_snapshot() {
  local output="$1"
  MYSQL_PWD="$PRODUCTION_PASSWORD" mysql --no-defaults --protocol=tcp --host="$PRODUCTION_HOST" \
    --port="$MYSQL_PORT" --user="$PRODUCTION_USER" "$PRODUCTION_DATABASE" \
    --batch --skip-column-names --execute="
      SELECT 'users',COUNT(*) FROM users UNION ALL
      SELECT 'production_batches',COUNT(*) FROM production_batches UNION ALL
      SELECT 'production_documents',COUNT(*) FROM production_documents UNION ALL
      SELECT 'warehouse_documents',COUNT(*) FROM warehouse_documents UNION ALL
      SELECT 'inventory_ledger',COUNT(*) FROM inventory_ledger UNION ALL
      SELECT 'purchase_orders',COUNT(*) FROM purchase_orders UNION ALL
      SELECT 'purchase_payments',COUNT(*) FROM purchase_payments UNION ALL
      SELECT 'sales_orders',COUNT(*) FROM sales_orders UNION ALL
      SELECT 'sales_receipts',COUNT(*) FROM sales_receipts UNION ALL
      SELECT 'cost_entries',COUNT(*) FROM cost_entries UNION ALL
      SELECT 'cost_settlements',COUNT(*) FROM cost_settlements UNION ALL
      SELECT 'audit_logs',COUNT(*) FROM audit_logs ORDER BY 1" > "$output"
}

reconcile_production() {
  local output="$1"
  env MYSQL_HOST="$PRODUCTION_HOST" MYSQL_PORT="$MYSQL_PORT" MYSQL_USER="$PRODUCTION_USER" \
    MYSQL_PASSWORD="$PRODUCTION_PASSWORD" MYSQL_DATABASE="$PRODUCTION_DATABASE" \
    "$RUNTIME_ROOT/.venv/bin/python" -m backend.scripts.reconcile_enterprise_data \
      --database "$PRODUCTION_DATABASE" --output "$output"
}

migrate_database() {
  local migration version checksum
  mysql "$DATABASE" < database/migrations/000_schema_migrations.sql
  for migration in database/migrations/[0-9][0-9][0-9]_*.sql; do
    [[ "$migration" == *000_schema_migrations.sql ]] && continue
    version="$(basename "$migration" .sql)"
    checksum="$(sha256sum "$migration" | awk '{print $1}')"
    mysql "$DATABASE" < "$migration"
    mysql "$DATABASE" --execute="INSERT INTO schema_migrations(version,checksum) VALUES ('${version}','${checksum}')"
  done
  mysql "$DATABASE" < database/seed_reference.sql
}

restore_nginx() {
  local temporary=/etc/nginx/conf.d/.adp-auth.conf.manual-test-restore
  install -o root -g root -m 0644 "$PREVIOUS_NGINX" "$temporary"
  mv -f -- "$temporary" "$NGINX_LIVE"
  nginx -t
  systemctl reload nginx
}

cd "$APP_ROOT"
curl --fail --silent --show-error http://127.0.0.1:5002/api/v1/health | grep -q '"environment":"production"'

PRODUCTION_HOST="$(env_value MYSQL_HOST)"
MYSQL_PORT="$(env_value MYSQL_PORT)"
PRODUCTION_USER="$(env_value MYSQL_USER)"
PRODUCTION_PASSWORD="$(env_value MYSQL_PASSWORD)"
PRODUCTION_DATABASE="$(env_value MYSQL_DATABASE)"
SERVER_NAME="$(env_value ADP_SERVER_NAME)"
TLS_CERT="$(env_value ADP_TLS_CERTIFICATE)"
TLS_KEY="$(env_value ADP_TLS_CERTIFICATE_KEY)"
[[ "$PRODUCTION_DATABASE" != "$DATABASE" && "$PRODUCTION_USER" != "$TEST_DB_USER" ]] || {
  echo "production and test identities must differ" >&2; exit 1;
}

[[ -z "$(mysql --batch --skip-column-names --execute="SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME='${DATABASE}'")" ]] || {
  echo "manual test database already exists" >&2; exit 1;
}
[[ "$(mysql --batch --skip-column-names --execute="SELECT COUNT(*) FROM mysql.user WHERE User='${TEST_DB_USER}'")" == "0" ]] || {
  echo "manual test database user already exists" >&2; exit 1;
}

install -d -o root -g adp -m 0750 "$TEST_ROOT"
install -d -o adp -g adp -m 0750 "$ATTACHMENTS"
install -o root -g root -m 0600 "$NGINX_LIVE" "$PREVIOUS_NGINX"
production_snapshot "$TEST_ROOT/production-before.rows"
reconcile_production "$TEST_ROOT/production-before-reconciliation.json"

TEST_PASSWORD="$(openssl rand -base64 24 | tr -d '\n')"
TEST_DB_PASSWORD="A!a1$(openssl rand -hex 22)"
FLASK_SECRET="$(openssl rand -hex 32)"
CSRF_SECRET="$(openssl rand -hex 32)"
temporary_credentials="$(mktemp /etc/adp/manual-test-credentials.env.XXXXXX)"
printf 'ADP_MANUAL_TEST_PASSWORD=%s\n' "$TEST_PASSWORD" > "$temporary_credentials"
install -o root -g root -m 0600 "$temporary_credentials" "$CREDENTIALS"
rm -f -- "$temporary_credentials"

mysql --execute="CREATE DATABASE \`${DATABASE}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
mysql <<SQL
CREATE USER '${TEST_DB_USER}'@'localhost' IDENTIFIED BY '${TEST_DB_PASSWORD}';
CREATE USER '${TEST_DB_USER}'@'127.0.0.1' IDENTIFIED BY '${TEST_DB_PASSWORD}';
GRANT ALL PRIVILEGES ON \`${DATABASE}\`.* TO '${TEST_DB_USER}'@'localhost';
GRANT ALL PRIVILEGES ON \`${DATABASE}\`.* TO '${TEST_DB_USER}'@'127.0.0.1';
SQL
migrate_database

temporary_env="$(mktemp /etc/adp/manual-test.env.XXXXXX)"
cat > "$temporary_env" <<EOF
APP_ENV=test
FLASK_SECRET_KEY=$FLASK_SECRET
CSRF_SECRET_KEY=$CSRF_SECRET
MYSQL_HOST=127.0.0.1
MYSQL_PORT=$MYSQL_PORT
MYSQL_DATABASE=$DATABASE
MYSQL_USER=$TEST_DB_USER
MYSQL_PASSWORD=$TEST_DB_PASSWORD
SESSION_COOKIE_SECURE=true
TRUSTED_PROXY_HOPS=1
ATTACHMENT_ROOT=$ATTACHMENTS
EOF
install -o root -g root -m 0600 "$temporary_env" "$TEST_ENV"
rm -f -- "$temporary_env"

set -a
source "$TEST_ENV"
source "$CREDENTIALS"
set +a
export ADP_MANUAL_TEST_CONFIRM=CREATE_TEST_DATA
export ADP_MANUAL_TEST_ATTACHMENT_DIR="$ATTACHMENTS"
"$RUNTIME_ROOT/.venv/bin/python" -m backend.scripts.manual_test_seed > "$TEST_ROOT/seed-manifest.json"
"$RUNTIME_ROOT/.venv/bin/python" -m backend.scripts.reconcile_enterprise_data \
  --database "$DATABASE" --output "$TEST_ROOT/test-reconciliation.json"
unset ADP_MANUAL_TEST_PASSWORD TEST_PASSWORD TEST_DB_PASSWORD

sed -e "s|__ADP_TEST_RELEASE_PATH__|$APP_ROOT|g" \
  -e "s|__ADP_RUNTIME_PATH__|$RUNTIME_ROOT|g" \
  deploy/adp-manual-test.service > "$TEST_ROOT/new-service"
! grep -q '__ADP_' "$TEST_ROOT/new-service"
install -o root -g root -m 0644 "$TEST_ROOT/new-service" /etc/systemd/system/adp-manual-test.service
systemctl daemon-reload
systemctl enable adp-manual-test
systemctl restart adp-manual-test
for _ in $(seq 1 30); do
  curl --fail --silent http://127.0.0.1:5003/api/v1/health | grep -q '"environment":"test"' && break
  sleep 1
done
curl --fail --silent --show-error http://127.0.0.1:5003/api/v1/health | grep -q '"environment":"test"'

sed -e "s|__ADP_SERVER_NAME__|$SERVER_NAME|g" \
  -e "s|__ADP_TLS_CERTIFICATE__|$TLS_CERT|g" \
  -e "s|__ADP_TLS_CERTIFICATE_KEY__|$TLS_KEY|g" \
  -e "s|__ADP_RELEASE_PATH__|$RUNTIME_ROOT|g" \
  -e "s|__ADP_TEST_RELEASE_PATH__|$APP_ROOT|g" \
  deploy/nginx-adp-manual-test.conf > "$TEST_ROOT/new-nginx.conf"
! grep -q '__ADP_' "$TEST_ROOT/new-nginx.conf"
temporary_nginx=/etc/nginx/conf.d/.adp-auth.conf.manual-test
install -o root -g root -m 0644 "$TEST_ROOT/new-nginx.conf" "$temporary_nginx"
mv -f -- "$temporary_nginx" "$NGINX_LIVE"
if ! nginx -t; then restore_nginx; exit 1; fi
if ! systemctl reload nginx; then restore_nginx; exit 1; fi

PUBLIC=(curl --fail --silent --show-error --resolve "$SERVER_NAME:443:127.0.0.1")
"${PUBLIC[@]}" "https://$SERVER_NAME/api/v1/health" | grep -q '"environment":"production"' || { restore_nginx; exit 1; }
"${PUBLIC[@]}" --cookie 'adp_environment=test' "https://$SERVER_NAME/api/v1/health" | grep -q '"environment":"test"' || { restore_nginx; exit 1; }

production_snapshot "$TEST_ROOT/production-after.rows"
cmp --silent "$TEST_ROOT/production-before.rows" "$TEST_ROOT/production-after.rows" || {
  restore_nginx; echo "production row counts changed" >&2; exit 1;
}
reconcile_production "$TEST_ROOT/production-after-reconciliation.json"
cmp --silent "$TEST_ROOT/production-before-reconciliation.json" \
  "$TEST_ROOT/production-after-reconciliation.json" || {
  restore_nginx; echo "production reconciliation changed" >&2; exit 1;
}

echo "manual test environment installed"
