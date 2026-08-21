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
# ── 两种模式，二选一（P2-34）──────────────────────────────────────────
#
#  设了 GEO_API_BASE → **HTTP worker 模式**：节点只出站 HTTP，不碰数据库。
#                      截图随结果传回 VPS，所以 SCREENSHOT_DIR 要**非空**。
#  没设             → **隧道模式**（原样）：直连 postgres，截图关闭。
#
# 回滚就是把 GEO_API_BASE 去掉重跑 start —— 不必 git revert（PHASE2 §6 规矩 1）。
API_BASE=${GEO_API_BASE:-}
if [ -n "$API_BASE" ]; then
  MODE=http
  # 复用现有的 X-API-Key（2026-08-18 拍板）。⚠️ 它折算成 superadmin，
  # 所以这台机器上放的是一把**超管等价凭证** —— 见 API.md §8.6 那段代价说明
  API_KEY=${GEO_API_KEY:?worker 模式需要 GEO_API_KEY（复用现有那把 X-API-Key）}
  DB_URL=""
  # 截图写在本地，由 provider 产出后随结果 multipart 传回 VPS
  SHOT_DIR=/data/screenshots
else
  MODE=tunnel
  # 数据库串走 tailnet。**VPS 上的 postgres 仍只绑 127.0.0.1**，
  # 由 `tailscale serve --tcp 5433 tcp://127.0.0.1:5433` 暴露给 tailnet（见 README）
  DB_URL=${GEO_DB_URL:?需要 GEO_DB_URL，例如 postgresql+psycopg://user:pass@100.64.240.17:5433/geo}
  API_KEY=""
  # 截图关闭：api 在 VPS，读不到本节点的目录，留着只会让证据页 404
  SHOT_DIR=""
fi
# P2-16 自动退避重试。**默认 false**：先只跑失败分类，在真实 run 上确认
# timeout 认得准（`grep kind=unknown`），再 `GEO_AUTO_RETRY=true ./deploy.sh start`。
# 回滚就是改回 false 重跑 start —— 不必 git revert（PHASE2 §6 规矩 1）
AUTO_RETRY=${GEO_AUTO_RETRY:-false}
# 两条 job 之间随机等 [PACE_MIN, PACE_MAX] 秒（P2-38 前置）。**默认 0 = 关**。
# 为什么要有它：run 298 量出来的起点间隔是 46/46/42/40/52/42/53/43 秒 ——
# 固定心跳本身就是一个行为指纹，而 CRAWL-INTEL §4.1 的结论是
# 「被盯上的不是量，是规律性」。回滚 = 去掉这两个变量重跑 start。
# ⚠️ 它会**拉长一次 run 的总时长**：49 条 job 配 20–90 秒 ≈ 多花 45 分钟。
PACE_MIN=${GEO_PACE_MIN:-0}
PACE_MAX=${GEO_PACE_MAX:-0}
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

# 传输用的临时目录（在 VPS 上）。收摊要在任何退出路径上都发生 ——
# 留下的是一个对 tailnet 可见的监听 + 一个 ~1GB 的文件，两样都不该过夜。
XFER_DIR=""
cleanup_xfer() {
  [ -n "$XFER_DIR" ] || return 0
  # **按精确 PID 关。** 绝不用 pkill -f 'http.server' 之类的模式匹配 ——
  # 两台机器上都跑着别的生产服务，误伤代价很高（README「已知问题」最后一条）
  vps "[ -s '$XFER_DIR/serve.pid' ] && kill \$(cat '$XFER_DIR/serve.pid') 2>/dev/null; rm -rf '$XFER_DIR'" \
    >/dev/null 2>&1 || true
  XFER_DIR=""
}
trap cleanup_xfer EXIT

do_image() {
  say "从 VPS 经 tailnet 传镜像"
  # **不从 mcr 拉。** 家宽拉那个 2GB 基础镜像要 90 分钟（实测 136KB/s 直连 /
  # 386KB/s 走代理），而 VPS 上本来就有构建好的镜像，经 tailnet 传只要一分钟。
  #
  # 这一步就是**唯一的代码更新路径** —— 容器只挂 /data，代码全在镜像里。
  #
  # ⚠️ **数据不能经过这台开发机。** 原先写的是
  #     vps "docker save $IMAGE | gzip -1" | node "gunzip | podman load"
  # 看着像 VPS 直连节点，其实两端都是**从开发机发起的 ssh** ——
  # 数据流是 `VPS → 开发机 → 节点`，开发机是中转。2026-08-16 实测这一跳的代价：
  #
  #   VPS → Mac                  656 KB/s
  #   Mac → 节点（**有线局域网**）  3 MB/s   ← 开发机自己就是瓶颈
  #   VPS ↔ 节点（tailnet 直连）   11 MB/s
  #
  # 922MB 传了 35 分钟没完，且卡住时三端进程全活着、谁都不报错。
  # 当时误判成「ssh 没保活」，加 ServerAliveInterval 并没有解决 —— 保活能救
  # 「连接断了」，救不了「路径本来就慢」。**真正的修法是把开发机摘出数据路径。**
  #
  # 现在开发机只发指令：VPS 导出成临时文件 → 起一个只绑 tailnet 地址的
  # http.server → 节点自己 curl 回来 → 无论成败都按精确 PID 收摊。
  local vps_host=${VPS#*@}   # GEO_VPS 的 host 部分就是 tailnet IP
  local port

  vps "command -v python3 >/dev/null" || { echo "  ✗ VPS 上没有 python3"; return 1; }

  # 这个 http 服务**对整个 tailnet 可见**，而 tailnet 上有别人的设备。四条约束：
  #  ① 只绑 tailnet 地址（--bind），公网不可达
  #  ② 目录名随机（mktemp），路径不可猜
  #  ③ 只服务这一个临时目录，不是 /tmp
  #  ④ 传完立刻关，不留任何持久配置（不用 tailscale serve --bg）
  XFER_DIR=$(vps "mktemp -d /tmp/geo-xfer-XXXXXXXX")
  port=$(( 39000 + RANDOM % 900 ))

  echo "  导出：$(vps "docker save $IMAGE | gzip -1 > $XFER_DIR/img.tgz && du -m $XFER_DIR/img.tgz | cut -f1") MB"

  vps "nohup python3 -m http.server $port --bind $vps_host --directory $XFER_DIR \
         > $XFER_DIR/serve.log 2>&1 & echo \$! > $XFER_DIR/serve.pid"
  sleep 2
  vps "kill -0 \$(cat $XFER_DIR/serve.pid)" || {
    echo "  ✗ http.server 没起来："; vps "cat $XFER_DIR/serve.log"; return 1; }

  # `--speed-limit` 是**卡住时唯一会说话的东西**：掉到 500KB/s 以下持续 30 秒
  # 就退出并报错。旧管道卡住时是静默挂着，只能靠人去看
  # `du -sm /var/lib/containers/storage` 涨不涨才判断得出来
  node "set -o pipefail; curl -sS --fail --speed-limit 500000 --speed-time 30 \
          http://$vps_host:$port/img.tgz | gunzip | podman load"

  cleanup_xfer
  echo "  VPS 侧镜像 build 于 $(vps "docker image inspect $IMAGE --format '{{.Created}}'")"
}

do_start() {
  say "起容器（模式：$MODE）"
  node "podman rm -f geo-crawler >/dev/null 2>&1 || true"
  # 两种模式只差这几个变量。
  # ⚠️ 凭证会短暂出现在节点的 `ps` 里（ssh 命令行）—— 隧道模式的 DATABASE_URL
  #    一直就是这样，worker 模式的 API_KEY 同理，**没有变好也没有变坏**。
  #    真要收掉得改成从 stdin 灌，那是另一件事。
  local mode_env
  if [ "$MODE" = http ]; then
    mode_env="-e WORKER_API_BASE='$API_BASE' -e API_KEY='$API_KEY'"
  else
    mode_env="-e DATABASE_URL='$DB_URL'"
  fi
  # ── 四条刻意为之，改之前先读 README ──
  #  --network host  直接用宿主的家宽出口，同时能走 tailnet 连 VPS 的 postgres
  #  不设任何 proxy  走代理出口会变成代理的落地，整个迁移就白做了（verify 会拦住）
  #  SCREENSHOT_DIR  **两种模式要求正好相反**：隧道模式必须为空（api 在 VPS，
  #                  读不到本节点的目录，留着只会让证据页 404）；worker 模式
  #                  必须非空（provider 得先截出图来，才有东西随结果传回去）。
  #                  切换时照抄另一种的配置 = 截图静默失效
  #  --shm-size=1g   Chromium 在容器里 /dev/shm 太小会崩
  #
  # DOUBAO_USER_DATA_DIR —— **豆包的 profile 必须持久**（2026-08-16 加）。
  # 不设它时 provider 每条 job 开一个 tempfile.TemporaryDirectory()、跑完删掉，
  # 于是豆包每次看到的是：**一个从未存在过的全新浏览器，带着一份已经用了
  # 好几天的 sessionid 登进来，问一个问题就消失**。而 seed_storage_state 只灌
  # cookies + localStorage —— IndexedDB / Cache / SW 每次都是空的，
  # 偏偏豆包加载了 s2-security-audit/-verify/-message 三个模块在做设备识别。
  # 「老会话 + 空白设备」这个组合本身就是矛盾的，真实用户不会这样。
  #
  # 这**不是 stealth 注入**，方向恰好相反：不是让指纹更假，是让设备身份连续 ——
  # 正是 `providers/browser.py` docstring 那条「出生环境要等于使用环境」。
  # 每次随机化指纹反而会更糟：豆包的惩罚是跨会话累积的（run 294/295 实测
  # 6 条 → 3 条），对纵向追踪的对手随机化设备等于送更强的信号。
  #
  # ⚠️ 依赖单 worker：Chromium 会给 profile 上锁，两条 job 并发会直接起不来。
  #    现在 FAKE_WORKER_BATCH_SIZE=1 串行，成立；P2-34 worker 化时要重新考虑。
  # 回滚：删掉这一行重跑 start，就回到每条 job 全新临时 profile。
  #
  # TONGYI_*（P2-06b）—— **千问从第一天就带持久 profile**，理由同上。
  # ⚠️ `tongyi_storage.json` 比另外两份敏感：用支付宝登录的话，cookies 里
  # 带着 `auth.alipay.com` / `securitycore.alipay.com` 的会话 ——
  # 泄露的后果不是「别人能用我们的千问账号」，是一个支付宝会话。
  # 送过来那条管道有 chmod 600，导出脚本也已补上（2026-08-16 之前是 644）。
  #
  # **DeepSeek 刻意不跟**（BACKEND §7.5）：它用旧路径跑了一年没出事，
  # 而调试新平台时不能同时改动唯一在工作的平台。
  node "podman run -d --name geo-crawler \
      --network host --shm-size=1g --restart=no \
      $mode_env \
      -e CRAWL_MODE=real \
      -e PLAYWRIGHT_HEADLESS=true \
      -e CRAWL_TIMEOUT_MS=120000 \
      -e DEEPSEEK_STORAGE_STATE=/data/deepseek_storage.json \
      -e DOUBAO_STORAGE_STATE=/data/doubao_storage.json \
      -e DOUBAO_USER_DATA_DIR=/data/doubao_profile \
      -e TONGYI_STORAGE_STATE=/data/tongyi_storage.json \
      -e TONGYI_USER_DATA_DIR=/data/tongyi_profile \
      -e SCREENSHOT_DIR='$SHOT_DIR' \
      -e CRAWL_AUTO_RETRY_ENABLED='$AUTO_RETRY' \
      -e CRAWL_PACE_MIN_SEC='$PACE_MIN' \
      -e CRAWL_PACE_MAX_SEC='$PACE_MAX' \
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

  # ④ 按模式分流。**两种模式要验的恰好是相反的事**
  if [ "$MODE" = http ]; then
    # ④a **P2-34 的验收条件本身**：这台机器上不该再有任何数据库凭证。
    #     摘掉它是整件事的主要目的 —— 不验的话，某次 start 忘了去掉
    #     DATABASE_URL 也不会有任何地方报错，而债其实还在
    if node "podman exec geo-crawler env" | grep -qE '^DATABASE_URL=.'; then
      echo "  ✗ 容器里仍有 DATABASE_URL —— worker 模式的意义就在于没有它"; ok=0
    else
      echo "  ✓ 容器无数据库凭证"
    fi

    # ④b api 可达且认这把 key。
    #
    #    **不能只 ping /health** —— 那是公开端点，key 错了照样 200，
    #    而节点会把 401 当成「没活干」静静跑一整夜。
    #
    #    ⚠️ **也绝不能拿 lease 来探活。** 自检要是真领走一条 job，就没人做完它，
    #    600 秒后被僵死回收成 failed —— 一条自检把真实数据毁了。
    #    用空 items 的 credentials 上报代替：同样要过鉴权、同样是 worker 命名空间，
    #    但循环体一次都不进，写不了任何东西（accepted: 0）
    if node "podman exec geo-crawler python -c \
      'import os,urllib.request as u; r=u.Request(os.environ[\"WORKER_API_BASE\"].rstrip(\"/\")+\"/v1/worker/credentials\", method=\"POST\", data=b\"{\\\"items\\\": []}\"); r.add_header(\"X-API-Key\", os.environ[\"API_KEY\"]); r.add_header(\"Content-Type\",\"application/json\"); u.urlopen(r, timeout=20).read()'" 2>/dev/null; then
      echo "  ✓ api 可达且鉴权通过（未触碰任何 job）"
    else
      echo "  ✗ worker 端点打不通（地址错 / key 错 / api 没起）"; ok=0
    fi

    # ④c 截图目录可写 —— worker 模式下它必须非空，否则截图静默失效
    if node "podman exec geo-crawler sh -c 'test -n \"\$SCREENSHOT_DIR\" && mkdir -p \"\$SCREENSHOT_DIR\" && test -w \"\$SCREENSHOT_DIR\"'"; then
      echo "  ✓ 截图目录可写"
    else
      echo "  ✗ SCREENSHOT_DIR 为空或不可写 —— 截图会静默失效（隧道模式才该为空）"; ok=0
    fi
  else
    # 隧道模式：数据库连得上
    if node "podman exec geo-crawler python -c \
      'import os,sqlalchemy as s; s.create_engine(os.environ[\"DATABASE_URL\"]).connect().close()'" 2>/dev/null; then
      echo "  ✓ 数据库可达"
    else
      echo "  ✗ 数据库连不上（检查 VPS 上的 tailscale serve）"; ok=0
    fi
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
