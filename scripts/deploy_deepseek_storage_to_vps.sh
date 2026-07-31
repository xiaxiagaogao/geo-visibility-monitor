#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PEM="${GEO_VPS_PEM:-$HOME/Desktop/pem/SG-DC1.pem}"
HOST="${GEO_VPS_HOST:-root@96.9.213.230}"
STATE="${1:-$ROOT/deploy/deepseek_storage.json}"

if [[ ! -f "$STATE" ]]; then
  echo "找不到 $STATE ，请先运行: python scripts/export_deepseek_storage.py"
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
# env file for compose
cat > .env << 'ENV'
CRAWL_MODE=real
FAKE_WORKER_ENABLED=false
DEEPSEEK_STORAGE_STATE=/data/deepseek_storage.json
PLAYWRIGHT_HEADLESS=true
FAKE_WORKER_BATCH_SIZE=1
FAKE_WORKER_INTERVAL_SEC=5
ENV
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

echo ">> 完成。可创建任务测试:"
echo "curl -s -X POST http://96.9.213.230:8200/v1/crawl-jobs -H 'Content-Type: application/json' -d '{\"prompt_id\":1,\"platform\":\"deepseek\",\"samples\":1}'"
