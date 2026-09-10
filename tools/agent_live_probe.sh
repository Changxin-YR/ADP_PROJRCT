#!/usr/bin/env bash
# Live ADP agent probe: drives 塘小助 through the real HTTP API on the deployed host.
#
# Usage (as root on the ADP host):
#   bash tools/agent_live_probe.sh turn   USER_ID '查询我的权限' [CONVERSATION_ID]
#   bash tools/agent_live_probe.sh cancel CONFIRMATION_ID USER_ID
#   bash tools/agent_live_probe.sh list   USER_ID            # 最近 10 条智能体审计记录
#
# Why it exists: the panel talks to POST /api/v1/agent/turn with a CSRF token, which is
# awkward to drive from a shell. A forged short-lived session row (deleted right after)
# plus `Authorization: Bearer` exercises the same endpoint without a browser.
set -uo pipefail

ACTION="${1:?usage: agent_live_probe.sh turn|cancel|list ...}"
BASE="${ADP_BASE:-https://23331.cloud/adp}"
ENV_FILE="${ADP_ENV_FILE:-/etc/adp/next.env}"

# shellcheck disable=SC1090
set -a; . "$ENV_FILE"; set +a
MY="mysql -h$MYSQL_HOST -P$MYSQL_PORT -u$MYSQL_USER -p$MYSQL_PASSWORD $MYSQL_DATABASE -N -B"

open_session() {  # open_session USER_ID -> echoes token
  local user_id="$1" token hash
  token="$(python3 -c 'import secrets;print(secrets.token_urlsafe(32))')"
  hash="$(python3 -c 'import hashlib,sys;print(hashlib.sha256(sys.argv[1].encode()).hexdigest())' "$token")"
  $MY -e "INSERT INTO sessions (user_id, session_token_hash, status, ip_address, user_agent, last_active_at, expires_at)
           VALUES ($user_id, '$hash', 'active', '127.0.0.1', 'agent-live-probe', NOW(), DATE_ADD(NOW(), INTERVAL 1 HOUR));" 2>/dev/null
  printf '%s' "$token"
}

close_session() {  # close_session TOKEN
  local hash
  hash="$(python3 -c 'import hashlib,sys;print(hashlib.sha256(sys.argv[1].encode()).hexdigest())' "$1")"
  $MY -e "DELETE FROM sessions WHERE session_token_hash='$hash';" 2>/dev/null
}

case "$ACTION" in
  turn)
    USER_ID="${2:?user id required}"
    MESSAGE="${3:?message required}"
    CONVERSATION_ID="${4:-probe-$(date +%s)-$RANDOM}"
    TOKEN="$(open_session "$USER_ID")"
    BODY="$(python3 -c 'import json,sys;print(json.dumps({"message":sys.argv[1],"conversation_id":sys.argv[2]}))' "$MESSAGE" "$CONVERSATION_ID")"
    START="$(date +%s.%N)"
    HTTP="$(curl -sS -o /tmp/adp-agent-probe.json -w '%{http_code}' -X POST "$BASE/api/v1/agent/turn" \
      -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -H 'X-Request-ID: probe0001' \
      --max-time 120 -d "$BODY")"
    END="$(date +%s.%N)"
    echo "=== turn HTTP $HTTP elapsed=$(python3 -c "print(round(float('$END')-float('$START'),2))")s conversation=$CONVERSATION_ID user=$USER_ID ==="
    python3 -c 'import json;print(json.dumps(json.load(open("/tmp/adp-agent-probe.json")),ensure_ascii=False,indent=2))' 2>/dev/null || cat /tmp/adp-agent-probe.json
    echo
    close_session "$TOKEN"
    echo "=== probe session removed ==="
    ;;
  cancel)
    CONFIRMATION_ID="${2:?confirmation id required}"
    USER_ID="${3:?user id required}"
    TOKEN="$(open_session "$USER_ID")"
    curl -sS -X POST "$BASE/api/v1/agent/cancel" -H "Authorization: Bearer $TOKEN" \
      -H 'Content-Type: application/json' -d "{\"confirmation_id\": $CONFIRMATION_ID}"; echo
    close_session "$TOKEN"
    $MY -e "select id, tool_name, status, user_id from agent_confirmations where id=$CONFIRMATION_ID" 2>/dev/null
    ;;
  list)
    USER_ID="${2:?user id required}"
    $MY -e "select id, object_ref, result, reason, created_at from audit_logs
             where action='agent_tool' and user_id=$USER_ID order by id desc limit 10" 2>/dev/null
    ;;
  *)
    echo "unknown action: $ACTION" >&2
    exit 2
    ;;
esac