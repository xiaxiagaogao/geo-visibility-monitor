#!/usr/bin/env bash
#
# 采集节点部署（P2-33）—— 把 crawler 部到一台**大陆出口**的机器上。
#
# 为什么存在：出口 IP 会影响 AI 的回答（PHASE2 §1.1 已在真实数据上验证），
# 而 VPS 在新加坡。所以 crawler 单独跑在大陆节点，其余组件留在 VPS。
#
# **不含任何凭证。** 主机、密钥、数据库串全从环境变量来；缺了就报错退出。
#
#   ./deploy.sh all        传镜像 → 起容器 → 自检（部署代码走这个）
#   ./deploy.sh image      只重传镜像
#   ./deploy.sh start      只重起容器（**用现有镜像，不更新代码**）
#   ./deploy.sh verify     只跑自检
#   ./deploy.sh logs       看日志
#
# ⚠️ **crawler 的代码在镜像里，不在节点的文件系统上。** 容器只挂 /data。
# 所以「更新代码」= 在 VPS 上重新 build（`git push vps main` 就会做）
# → `./deploy.sh all` 把新镜像传过来。`start` 单用只是换个容器跑同一份旧代码。
#
set -euo pipefail

NODE=${GEO_NODE:?需要 GEO_NODE，例如 root@192.168.2.60}
NODE_KEY=${GEO_NODE_KEY:?需要 GEO_NODE_KEY，指向该节点的 ssh 私钥}
VPS=${GEO_VPS:?需要 GEO_VPS，例如 root@100.64.240.17（走 tailnet）}
VPS_KEY=${GEO_VPS_KEY:?需要 GEO_VPS_KEY}
# 数据库串走 tailnet。**VPS 上的 postgres 仍只绑 127.0.0.1**，
# 由 `tailscale serve --tcp 5433 tcp://127.0.0.1:5433` 暴露给 tailnet（见 README）
DB_URL=${GEO_DB_URL:?需要 GEO_DB_URL，例如 postgresql+psycopg://user:pass@100.64.240.17:5433/geo}
# P2-16 自动退避重试。**默认 false**：先只跑失败分类，在真实 run 上确认
# timeout 认得准（`grep kind=unknown`），再 `GEO_AUTO_RETRY=true ./deploy.sh start`。
# 回滚就是改回 false 重跑 start —— 不必 git revert（PHASE2 §6 规矩 1）
AUTO_RETRY=${GEO_AUTO_RETRY:-false}
# 浏览器上报的时区 + 期望的登录态签发地。
# **这两个和「crawler 跑在哪台机器上」是同一件事的三个面**：
# 切到 VPS 冷备（新加坡出口）时，两个都要跟着改，否则只是把一种不一致
# 换成另一种 —— 2026-08-15 那次就是「IP 切了、时区和登录态没切」。
TZ_ID=${GEO_TZ:-Asia/Shanghai}
EXPECT_REGION=${GEO_EXPECT_REGION:-cn}
# 这台机器的标签，随健康度一起上报（P2-36 的第一块）
NODE_LABEL=${GEO_NODE_LABEL:-changsha-home}

IMAGE=deploy-crawler:latest
NODE_DATA=/opt/geo-crawl-data

# **ServerAlive 不能省。** 传镜像那条管道要跑好几分钟，中途连接断掉时
# ssh 不会报错、也不会退出 —— 数据停了、进程还挂着，表现是「传了 35 分钟
# 还没完」而 podman load 的 CPU 是 0（2026-08-15 实际卡过一次）。
# 加上保活，断了 60 秒内自己退出并报错。
SSH_KEEPALIVE="-o ServerAliveInterval=20 -o ServerAliveCountMax=3"
node() { ssh -i "$NODE_KEY" -o BatchMode=yes -o ConnectTimeout=20 $SSH_KEEPALIVE "$NODE" "$@"; }
vps()  { ssh -i "$VPS_KEY"  -o BatchMode=yes -o ConnectTimeout=20 $SSH_KEEPALIVE "$VPS"  "$@"; }
say()  { printf '\n\033[1m▸ %s\033[0m\n' "$*"; }

do_image() {
  say "从 VPS 经 tailnet 传镜像"
  # **不从 mcr 拉。** 家宽拉那个 2GB 基础镜像要 90 分钟（实测 136KB/s 直连 /
  # 386KB/s 走代理），而 VPS 上本来就有构建好的镜像，经 tailnet 传只要一分钟。
  #
  # 这一步就是**唯一的代码更新路径** —— 容器只挂 /data，代码全在镜像里。
  vps "docker save $IMAGE | gzip -1" | node "gunzip | podman load"
  echo "  VPS 侧镜像 build 于 $(vps "docker image inspect $IMAGE --format '{{.Created}}'")"
}

do_start() {
  say "起容器"
  node "podman rm -f geo-crawler >/dev/null 2>&1 || true"
  # ── 四条刻意为之，改之前先读 README ──
  #  --network host  直接用宿主的家宽出口，同时能走 tailnet 连 VPS 的 postgres
  #  不设任何 proxy  走代理出口会变成代理的落地，整个迁移就白做了（verify 会拦住）
  #  SCREENSHOT_DIR= 截图关闭：api 在 VPS，读不到本节点的截图目录，
  #                  留着只会让证据页 404。P2-34 worker 化之后随结果传回即可恢复
  #  --shm-size=1g   Chromium 在容器里 /dev/shm 太小会崩
  node "podman run -d --name geo-crawler \
      --network host --shm-size=1g --restart=no \
      -e DATABASE_URL='$DB_URL' \
      -e CRAWL_MODE=real \
      -e PLAYWRIGHT_HEADLESS=true \
      -e CRAWL_TIMEOUT_MS=120000 \
      -e DEEPSEEK_STORAGE_STATE=/data/deepseek_storage.json \
      -e DOUBAO_STORAGE_STATE=/data/doubao_storage.json \
      -e SCREENSHOT_DIR= \
      -e CRAWL_AUTO_RETRY_ENABLED='$AUTO_RETRY' \
      -e CRAWL_TIMEZONE_ID='$TZ_ID' \
      -e CRAWL_EXPECTED_CREDENTIAL_REGION='$EXPECT_REGION' \
      -e CRAWL_NODE_LABEL='$NODE_LABEL' \
      -e FAKE_WORKER_INTERVAL_SEC=5 \
      -e FAKE_WORKER_BATCH_SIZE=1 \
      -v $NODE_DATA:/data:rw,Z \
      $IMAGE" >/dev/null
  sleep 6
  node "podman ps --filter name=geo-crawler --format '  {{.Names}}  {{.Status}}'"
}

do_verify() {
  say "自检"
  local ok=1

  # ① storage_state 在不在 —— 不在的话每一条抓取都会失败在登录页
  if node "test -s $NODE_DATA/deepseek_storage.json"; then
    echo "  ✓ storage_state 存在"
  else
    echo "  ✗ $NODE_DATA/deepseek_storage.json 缺失或为空"; ok=0
  fi

  # ② 容器里没有 proxy 环境变量
  if node "podman exec geo-crawler env" | grep -qiE '^(http|https|all)_proxy='; then
    echo "  ✗ 容器里有 proxy 环境变量 —— 出口会变成代理的落地"; ok=0
  else
    echo "  ✓ 容器无 proxy 环境变量"
  fi

  # ③ **最重要的一条**：容器出口 ≠ 代理出口。
  #    这是唯一会静默毁掉整件事的错误 —— 走了代理，数据照样采得到，
  #    只是全部来自错误的地理位置，而没有任何地方会报错。
  local direct proxied
  direct=$(node "podman exec geo-crawler python -c \
    'import urllib.request as u; print(u.urlopen(\"https://ipinfo.io/ip\", timeout=15).read().decode().strip())'" 2>/dev/null || echo "")
  proxied=$(node "curl -s --max-time 12 -x http://127.0.0.1:7890 https://ipinfo.io/ip" 2>/dev/null || echo "")
  if [ -z "$direct" ]; then
    echo "  ✗ 取不到容器出口 IP"; ok=0
  elif [ -n "$proxied" ] && [ "$direct" = "$proxied" ]; then
    echo "  ✗ 容器出口 ($direct) == 代理出口 —— 走代理了，迁移失效"; ok=0
  else
    echo "  ✓ 容器出口 $direct${proxied:+（代理出口是 $proxied，两者不同）}"
  fi

  # ④ 数据库连得上
  if node "podman exec geo-crawler python -c \
    'import os,sqlalchemy as s; s.create_engine(os.environ[\"DATABASE_URL\"]).connect().close()'" 2>/dev/null; then
    echo "  ✓ 数据库可达"
  else
    echo "  ✗ 数据库连不上（检查 VPS 上的 tailscale serve）"; ok=0
  fi

  # ⑤ 跑的是哪一份代码 —— **不判定成功失败，只把它摆出来**。
  #    代码全在镜像里，而「镜像旧了」这件事不会有任何地方报错：容器照常起、
  #    照常采集，只是跑的是上一版。2026-08-15 就踩过一次
  #    （以为 `deploy.sh sync` 更新了代码，其实那个目录根本没被挂载）。
  #
  #    ⚠️ 必须 inspect **容器所用的那个镜像**，不能 inspect 容器本身 ——
  #    `podman inspect <容器>` 的 `.Created` 是**容器**的创建时间，
  #    每次 start 都是「刚刚」，恰恰查不出唯一该查的那件事。这条也踩过。
  local img_built
  img_built=$(node 'i=$(podman inspect geo-crawler --format "{{.Image}}"); podman image inspect "$i" --format "{{.Created}}"' 2>/dev/null || echo "取不到")
  echo "  · 容器所用镜像 build 于 $img_built"
  echo "    比 VPS 上那次 build 旧就 ./deploy.sh image 重传（VPS 侧 build 由 git push vps main 触发）"

  [ "$ok" = 1 ] && echo "  —— 自检通过" || { echo "  —— 自检失败"; return 1; }
}

case "${1:-all}" in
  image)  do_image ;;
  start)  do_start ;;
  verify) do_verify ;;
  logs)   node "podman logs --tail ${2:-30} geo-crawler" ;;
  all)
    # **每次都重传镜像。** 原先是「镜像已存在就跳过」，配上那个没人读的 sync，
    # 结果是改完代码跑 all 什么都没更新 —— 而且不报错。传一次约一分钟，
    # 拿这一分钟换「all 一定是当前代码」，值得
    do_image
    do_start
    do_verify
    ;;
  *) sed -n '2,22p' "$0"; exit 2 ;;
esac
