#!/bin/bash
# 真正的部署步骤。由 $GIT_DIR/hooks/post-receive（存根，见 post-receive.hook）
# 在 checkout 之后 exec 进来 —— 所以本文件开始执行时内容已经定稿，不存在
# "边跑边被自己改写"。也可以在 VPS 上手动跑：/opt/geo-demo/deploy/deploy.sh
#
# stdout/stderr 由存根重定向到 /var/log/geo-demo-deploy.log（exec 继承）；
# 手动跑时直接打在终端上。
set -euo pipefail

TARGET="${TARGET:-/opt/geo-demo}"
GIT_DIR="${GIT_DIR:-/opt/geo-demo.git}"
HOOK="$GIT_DIR/hooks/post-receive"

# 存根有更新就装上（下次 push 生效）。在这里改它是安全的：当前执行的是本文件，
# 不是存根。旧的留一份 .prev —— 存根一旦坏掉所有部署都完蛋，要能手动 cp 回去。
if [ -f "$TARGET/deploy/post-receive.hook" ] && ! cmp -s "$TARGET/deploy/post-receive.hook" "$HOOK"; then
  echo "存根有更新：备份到 $HOOK.prev，装新版（下次 push 生效）"
  cp -p "$HOOK" "$HOOK.prev" 2>/dev/null || true
  cp "$TARGET/deploy/post-receive.hook" "$HOOK"
  chmod +x "$HOOK"
fi

cd "$TARGET/deploy"
echo "docker compose up postgres api web..."
docker compose up -d --build postgres api web

# crawler holds Playwright code; rebuild if container already exists
if docker ps -a --format '{{.Names}}' | grep -qx geo-crawler; then
  echo "docker compose rebuild crawler..."
  docker compose --profile crawl up -d --build crawler
  # storage_state lives on volume /data; re-seed only if missing
  if [ -f deepseek_storage.json ]; then
    if ! docker exec geo-crawler test -f /data/deepseek_storage.json 2>/dev/null; then
      echo "seed deepseek_storage.json into crawler volume"
      docker cp deepseek_storage.json geo-crawler:/data/deepseek_storage.json || true
    fi
  fi
fi
for i in $(seq 1 90); do
  if docker exec geo-postgres pg_isready -U geo -d geo >/dev/null 2>&1; then
    echo "postgres ready"
    break
  fi
  sleep 1
done
for i in $(seq 1 60); do
  if curl -sf http://127.0.0.1:8200/health >/dev/null 2>&1; then
    echo "api ready"
    break
  fi
  sleep 2
done
docker compose ps
# /health 是公开探针；/health/db 与 /health/config 已需要 API_KEY，部署脚本不再探
curl -s http://127.0.0.1:8200/health || true
echo
# 前端探针：Caddy 把非 /v1 /qa /health 的请求转到 3000，这里直连确认进程活着
for i in $(seq 1 30); do
  if curl -sf -o /dev/null http://127.0.0.1:3000/login; then
    echo "web ready"
    break
  fi
  sleep 2
done
if ! grep -qE '^API_KEY=.+' .env 2>/dev/null; then
  echo "!! 警告：deploy/.env 未设置 API_KEY —— 8200 端口在公网上完全无鉴权"
fi
echo "deploy finished"
