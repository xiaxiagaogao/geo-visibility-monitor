# 采集节点（大陆出口）

> **为什么要有这个东西**：出口 IP 会影响 AI 的回答 —— 这不是推测，是 2026-08-14
> 在真实数据上验证过的（`docs/PHASE2.md` §3「零」）。而 VPS 在新加坡、服务对象是
> 大陆用户、要接的三个平台（豆包 · 千问 · Kimi）全是大陆服务。
>
> 所以只有 **crawler** 跑在大陆节点，`api` / `web` / `postgres` 仍在 VPS。

## 拓扑

```text
              tailnet 直连 116ms / 21MB/s
 采集节点 ←─────────────────────────────→ sg-dc1 (100.64.240.17)
 podman · Fedora                          docker · Ubuntu
 ┌──────────────────┐                    ┌────────────────────┐
 │ geo-crawler      │                    │ geo-api    :8200   │
 │  --network host  │── DATABASE_URL ───▶│ geo-web    :3000   │
 │  无 proxy        │  100.64.240.17:5433│ geo-postgres       │
 │  出口 = 家宽     │                    │  只绑 127.0.0.1    │
 │  截图关闭        │                    │ geo-crawler【冷备】│
 └──────────────────┘                    └────────────────────┘
```

## 部署

```bash
export GEO_NODE=root@192.168.2.60
export GEO_NODE_KEY=~/path/to/node.pem
export GEO_VPS=root@100.64.240.17          # 走 tailnet，公网那条 SSH 常抖
export GEO_VPS_KEY=~/path/to/vps.pem
export GEO_DB_URL='postgresql+psycopg://USER:PASS@100.64.240.17:5433/geo'

./deploy.sh all
```

脚本**不含任何凭证**，全从环境变量来，缺了直接报错退出。

自动退避重试（P2-16）默认关。观察一轮确认分类没问题后再打开：

```bash
GEO_AUTO_RETRY=true ./deploy.sh start     # 回滚 = 去掉这个变量重跑 start
```

## 四条不能改的，改之前先读这里

### 1. 容器绝对不能走代理

节点上可能装着代理（我们这台是 mihomo 在 `7890`）。**走代理出口就变成代理的落地**
——我们这台走代理是香港 `42.200.231.233`，直连才是长沙移动 `36.157.231.164`。

**这是唯一会静默毁掉整件事的错误**：走了代理，数据照样采得到，只是全部来自错误
的地理位置，而没有任何地方会报错。所以 `deploy.sh verify` 里有一条硬检查 ——
**容器出口 ≠ 代理出口**，相等就直接判失败。

> 例外：**build 时可以走代理**（只是取个镜像，与出口无关）。
> 但我们现在根本不在节点上 build，见下。

### 2. 镜像从 VPS 传，不从 mcr 拉

家宽拉那个 2GB 的 Playwright 基础镜像：直连 136KB/s、走代理 386KB/s ——
**要 90 分钟**。而 VPS 上本来就有构建好的镜像，`docker save` 经 tailnet 传
**只要 66 秒**（21MB/s）。

所以节点上**不 build**，只 `podman load`。代码更新走 `deploy.sh sync`
（`git archive` 推当前 HEAD 的干净内容）；只有 Dockerfile 变了才需要在 VPS 上
重新 build 再 `deploy.sh image` 重传。

### 3. postgres 不改绑定

VPS 上的 postgres **仍然只绑 `127.0.0.1:5433`**。给 tailnet 的访问是靠：

```bash
tailscale serve --bg --tcp 5433 tcp://127.0.0.1:5433
```

**别为了省事把它改成 `0.0.0.0`** —— 那等于把数据库端口开到公网，靠防火墙兜底。
现在的姿势是：暴露面完全由 tailnet 决定，公网验证过连不上。

### 4. 截图是关着的，这是有意的

`api` 和 `crawler` 原本共享一个 volume，截图靠它工作。crawler 搬走之后，
写在节点上的截图 VPS 读不到 —— **留着只会让证据页 404**。

所以 `SCREENSHOT_DIR=` 置空，证据页那个「查看截图」按钮条件渲染、直接不显示。
**降级是干净的。** `P2-34` worker 化之后随结果 multipart 传回即可恢复。

## 冷备切换

VPS 上那台 `geo-crawler` **停着**，是冷备：

```bash
# 采集节点挂了 → 启用冷备
ssh root@100.64.240.17 'docker start geo-crawler'

# 采集节点恢复了 → 停掉冷备
ssh root@100.64.240.17 'docker stop geo-crawler'
```

### ⚠️ 冷备是「接替」，不是「并行」

技术上两个 crawler **不会**抢到同一条 job ——
`services/crawl_jobs.claim_pending_jobs` 用的是 `FOR UPDATE SKIP LOCKED`
（那个函数的 docstring 写「single-worker safe enough for demo」，低估了自己）。

**但仍然不能并行**：那样一次 run 的样本会同时来自新加坡和大陆两个出口，
而迁移的全部理由就是出口影响回答。更隐蔽的是 —— **数据里没有任何字段记录
某条样本是哪台机器采的**（`PHASE2` P2-36），混了就分不开、事后也查不出来。

**启用冷备时必须意识到：从那一刻起采集出口换回了新加坡**，
那段数据与前后不可比。

### 部署曾经会把冷备静默拉起来（2026-08-14 已修）

旧判断是「容器存在就 `compose up -d`」，而 `docker ps -a | grep -qx geo-crawler`
**连已停止的容器一起匹配** —— 于是每推一次代码，冷备就被启用一次，
而没有任何地方会报错。P2-35 那次部署实际让它跑了 4 小时，
只是碰巧那段时间没人发起 run 才没污染数据。

现在 `deploy/deploy.sh` 按容器原本的状态分流：在跑的 `up -d --build`，
停着的走 **`compose create --build`** —— 重建但从头到尾不启动。

**照样 rebuild 是有意的**：冷备切换的动作是 `docker start`，
只 build 不重建容器的话，那一刻起来的还是旧代码。

## 已知问题

| | |
|---|---|
| **冷启动被限流** | 一次 run 开头的头一两条常见 `Page.goto` 120 秒超时，之后就顺。**P2-16 已做**：这类失败分类成 `timeout`，自动退避重排（30s → 60s，最多 3 次）。开关 `CRAWL_AUTO_RETRY_ENABLED`，见 `BACKEND.md` §7.2。手动 `POST /v1/crawl-jobs/{id}/retry` 仍然可用，且会把计数清零 |
| **家宽 IP 是动态的** | tailscale 自己能重连；但风控与 `storage_state` 会不会受影响，没验过 |
| **节点不是独占的** | 我们这台还跑着别的服务。任何 `pkill` / `pgrep` **都要按精确 PID** —— 模式匹配会误伤 |
| **`storage_state` 会过期** | 过期的表现是**一批 job 全 failed**，和「平台没接」「网络问题」的排查方向完全不同。`PHASE2` P2-07 要做可观测性 |

## storage_state 怎么送过去

它是凭证，**不进 Git**（`BACKEND.md` 的既有规矩）。从 VPS 直接管道到节点，
中间不落盘：

```bash
ssh -n -i "$GEO_VPS_KEY" "$GEO_VPS" 'docker exec geo-crawler cat /data/deepseek_storage.json' \
| ssh -i "$GEO_NODE_KEY" "$GEO_NODE" \
    'cat > /opt/geo-crawl-data/deepseek_storage.json && chmod 600 $_'
```

传完对一下字节数，两边应该一致。
