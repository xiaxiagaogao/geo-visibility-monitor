#!/usr/bin/env bash
# 将 main 推送到 VPS 裸仓库并触发 post-receive 部署
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PEM="${GEO_VPS_PEM:-$HOME/Desktop/pem/SG-DC1.pem}"
HOST="${GEO_VPS_HOST:-root@96.9.213.230}"
REMOTE_URL="${GEO_VPS_GIT:-$HOST:/opt/geo-demo.git}"

if [[ ! -f "$PEM" ]]; then
  echo "找不到私钥: $PEM"
  echo "请设置 GEO_VPS_PEM=/path/to/key.pem"
  exit 1
fi

chmod 400 "$PEM" || true
export GIT_SSH_COMMAND="ssh -i $PEM -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new"

if ! git remote get-url vps >/dev/null 2>&1; then
  git remote add vps "$REMOTE_URL"
else
  git remote set-url vps "$REMOTE_URL"
fi

echo ">> remote: $(git remote get-url vps)"
echo ">> pushing main..."
git push vps main
echo ">> done. 上机检查: ssh -i $PEM $HOST 'docker ps --filter name=geo-'"
