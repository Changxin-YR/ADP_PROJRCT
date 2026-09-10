#!/usr/bin/env bash
set -Eeuo pipefail

: "${ADP_VERIFY_IDENTIFIER:?请设置 ADP_VERIFY_IDENTIFIER 作为验收登录账号}"
: "${ADP_VERIFY_PASSWORD:?请设置 ADP_VERIFY_PASSWORD 作为验收登录密码}"

SERVER_NAME="${ADP_SERVER_NAME:-23331.cloud}"
BASE="${ADP_PUBLIC_BASE_URL:-https://${SERVER_NAME}/adp}"
BASE="${BASE%/}"
[[ "$BASE" == "https://${SERVER_NAME}" || "$BASE" == "https://${SERVER_NAME}/adp" ]] || {
  echo "ADP_PUBLIC_BASE_URL 必须是 https://${SERVER_NAME} 或 https://${SERVER_NAME}/adp" >&2
  exit 1
}

COOKIE_JAR="$(mktemp)"
trap 'rm -f -- "$COOKIE_JAR"' EXIT
CURL=(curl --fail --silent --show-error --connect-timeout 10 --max-time 30 --resolve "${SERVER_NAME}:443:127.0.0.1")

json_field() {
  python -c 'import json,sys; value=json.load(sys.stdin); print(value'"$1"')'
}

assert_ok() {
  local payload="$1"
  printf '%s' "$payload" | python -c 'import json,sys; value=json.load(sys.stdin); assert value.get("code") == "OK", value'
}

"${CURL[@]}" "$BASE/healthz" | grep -qx 'ok'
assert_ok "$("${CURL[@]}" "$BASE/api/v1/health")"
page="$("${CURL[@]}" "$BASE/auth/login")"
grep -q '<div id="app">' <<<"$page"

csrf_response="$("${CURL[@]}" -c "$COOKIE_JAR" "$BASE/api/v1/auth/csrf")"
csrf_token="$(printf '%s' "$csrf_response" | json_field '["data"]["csrf_token"]')"
login_payload="$(python -c 'import json,os; print(json.dumps({"identifier": os.environ["ADP_VERIFY_IDENTIFIER"], "password": os.environ["ADP_VERIFY_PASSWORD"]}))')"
login_response="$("${CURL[@]}" -b "$COOKIE_JAR" -c "$COOKIE_JAR" -H "Content-Type: application/json" -H "X-CSRF-Token: $csrf_token" --data "$login_payload" "$BASE/api/v1/auth/login")"
assert_ok "$login_response"
assert_ok "$("${CURL[@]}" -b "$COOKIE_JAR" "$BASE/api/v1/auth/me")"
assert_ok "$("${CURL[@]}" -b "$COOKIE_JAR" "$BASE/api/v1/auth/workbench")"
if [[ "${ADP_SKIP_BROWSER_CHECK:-0}" != "1" ]]; then
  DOMAIN_CUTOVER_IDENTIFIER="$ADP_VERIFY_IDENTIFIER" \
  DOMAIN_CUTOVER_PASSWORD="$ADP_VERIFY_PASSWORD" \
  PLAYWRIGHT_BASE_URL="${BASE}/" \
    npm --prefix frontend run test:e2e -- tests/e2e/domain-cutover.spec.ts
fi
echo "domain verification passed: ${BASE}"
