#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PEM="${GEO_VPS_PEM:-$HOME/Desktop/pem/SG-DC1.pem}"
HOST="${GEO_VPS_HOST:-root@203.0.113.20}"
STATE="${1:-$ROOT/deploy/deepseek_storage.json}"

if [[ ! -f "$STATE" ]]; then
  echo "找不到 $STATE ，请先运行: python scripts/export_storage_state.py"
  exit 1
fi
if [[ ! -f "$PEM" ]]; then
  echo "找不到密钥 $PEM"
  exit 1
fi
chmod 400 "$PEM" || true

echo ">> 上传 storage_state 到 VPS..."
scp -i "$PEM" -o IdentitiesOnly=yes "$STATE" "$HOST:/opt/geo-demo/deploy/deepseek_storage.json"

echo ">> 配置并启动 crawler (real mode)..."
ssh -i "$PEM" -o IdentitiesOnly=yes "$HOST" 'bash -s' << 'REMOTE'
set -e
cd /opt/geo-demo/deploy
# 保留已有 API_KEY；没有就生成一个（绝不能把公网 8200 裸奔出去）
API_KEY="$(sed -n 's/^API_KEY=\(.\+\)$/\1/p' .env 2>/dev/null | head -1 || true)"
if [ -z "$API_KEY" ]; then
  API_KEY="$(head -c 32 /dev/urandom | base64 | tr -d '=+/' | cut -c1-43)"
  echo ">> 已生成新 API_KEY（下方输出，请自行保存）"
fi
# env file for compose
cat > .env << ENV
CRAWL_MODE=real
FAKE_WORKER_ENABLED=false
DEEPSEEK_STORAGE_STATE=/data/deepseek_storage.json
PLAYWRIGHT_HEADLESS=true
FAKE_WORKER_BATCH_SIZE=1
FAKE_WORKER_INTERVAL_SEC=5
API_KEY=$API_KEY
API_COOKIE_SECURE=false
ENV
chmod 600 .env
echo "API_KEY=$API_KEY"
# ensure volume dir file via docker cp after crawler up
docker compose up -d api
docker compose --profile crawl up -d --build crawler
# copy state into crawler volume mount path used by container
# compose mounts crawl_data:/data — copy into running container
docker cp /opt/geo-demo/deploy/deepseek_storage.json geo-crawler:/data/deepseek_storage.json
docker restart geo-crawler
sleep 3
docker ps --filter name=geo- --format "table {{.Names}}\t{{.Status}}"
echo "CRAWL_MODE on api:"
curl -s http://127.0.0.1:8200/health || true
echo
echo "crawler logs (tail):"
docker logs --tail 30 geo-crawler || true
REMOTE

echo ">> 完成。可创建任务测试（把 \$API_KEY 换成上面输出的密钥）:"
echo "curl -s -X POST http://203.0.113.20:8200/v1/crawl-jobs \\"
echo "  -H 'Content-Type: application/json' -H \"X-API-Key: \$API_KEY\" \\"
echo "  -d '{\"prompt_id\":1,\"platform\":\"deepseek\",\"samples\":1}'"
