#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "$(id -u)" != "0" ]]; then
  echo "请使用 root 执行此脚本。" >&2
  exit 1
fi

APP_ROOT="${APP_ROOT:-/opt/adp/login-registration}"
PYTHON_BIN="${PYTHON_BIN:-/opt/adp-venv/bin/python}"

command -v nginx >/dev/null 2>&1 || { echo "未找到 nginx，请先安装并启动 Nginx。" >&2; exit 1; }
command -v mysql >/dev/null 2>&1 || { echo "未找到 mysql 客户端，请先安装 MySQL 客户端。" >&2; exit 1; }
test -x "$PYTHON_BIN" || { echo "未找到 $PYTHON_BIN，请确认 Python 虚拟环境已经准备好。" >&2; exit 1; }

id adp >/dev/null 2>&1 || useradd --system --home-dir "$APP_ROOT" --shell /sbin/nologin adp
install -d -o adp -g adp -m 0750 "$APP_ROOT"
install -d -o root -g root -m 0750 /etc/adp

install -o root -g root -m 0644 "$APP_ROOT/实现文档/登陆注册/deploy/adp-auth.service" /etc/systemd/system/adp-auth.service

systemctl daemon-reload
systemctl enable nginx adp-auth
nginx -t

echo "基础服务文件已安装。请先准备域名或受信任 IP 证书，并按 08-CentOS部署与上线.md 创建 /etc/adp/auth.env，再执行 deploy.sh 生成 TLS 站点配置。"
