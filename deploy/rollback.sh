#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "$(id -u)" != "0" ]]; then
  echo "请使用 root 执行此脚本。" >&2
  exit 1
fi

APP_ROOT="${APP_ROOT:-/opt/adp/login-registration}"
BACKUP_ROOT="${BACKUP_ROOT:-/opt/adp/backups}"
LATEST_BACKUP="$(find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d -printf '%T@ %p\n' 2>/dev/null | sort -nr | awk 'NR==1 {print $2}')"

if [[ -z "$LATEST_BACKUP" || ! -d "$LATEST_BACKUP/登陆注册" ]]; then
  echo "没有可用的发布备份，停止回滚。" >&2
  exit 1
fi

mv "$APP_ROOT/实现文档/登陆注册" "$APP_ROOT/实现文档/登陆注册.failed.$(date +%Y%m%d%H%M%S)"
cp -a "$LATEST_BACKUP/登陆注册" "$APP_ROOT/实现文档/登陆注册"
chown -R adp:adp "$APP_ROOT"
chmod 0755 "$APP_ROOT" "$APP_ROOT/实现文档" "$APP_ROOT/实现文档/登陆注册"
nginx -t
systemctl restart adp-auth
systemctl reload nginx
curl --fail --silent --show-error http://127.0.0.1:5001/api/v1/health >/dev/null
echo "已回滚到 $LATEST_BACKUP。"
