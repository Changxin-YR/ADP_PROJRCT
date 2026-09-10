#!/usr/bin/env bash
set -Eeuo pipefail

[[ $# == 1 || $# == 2 ]] || {
  echo "用法：ADP_SERVER_NAME=23331.cloud $0 RELEASE_PATH [BACKEND_PORT]" >&2
  exit 2
}

SERVER_NAME="${ADP_SERVER_NAME:-23331.cloud}"
RELEASE_PATH="$1"
BACKEND_PORT="${2:-5002}"
PUBLIC_PATH="${ADP_PUBLIC_PATH:-/adp/}"
[[ "$SERVER_NAME" =~ ^[A-Za-z0-9.-]+$ ]] || { echo "ADP_SERVER_NAME 格式无效" >&2; exit 1; }
[[ "$RELEASE_PATH" == /* && "$RELEASE_PATH" != *'|'* ]] || { echo "RELEASE_PATH 必须是安全的绝对路径" >&2; exit 1; }
[[ "$BACKEND_PORT" =~ ^[0-9]+$ ]] || { echo "BACKEND_PORT 格式无效" >&2; exit 1; }
[[ "$PUBLIC_PATH" =~ ^/[A-Za-z0-9._~-]+/$ ]] || { echo "ADP_PUBLIC_PATH 必须是单层绝对路径并以 / 结尾" >&2; exit 1; }
PUBLIC_PREFIX="${PUBLIC_PATH%/}"

sed \
  -e "s|__ADP_SERVER_NAME__|$SERVER_NAME|g" \
  -e "s|__ADP_RELEASE_PATH__|$RELEASE_PATH|g" \
  -e "s|__ADP_BACKEND_PORT__|$BACKEND_PORT|g" \
  -e "s|__ADP_PUBLIC_PATH__|$PUBLIC_PATH|g" \
  -e "s|__ADP_PUBLIC_PREFIX__|$PUBLIC_PREFIX|g" \
  "$(dirname "$0")/nginx-adp-shared-location.conf"
