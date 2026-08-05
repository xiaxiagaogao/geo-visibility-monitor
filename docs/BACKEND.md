# GEO Demo · 后端说明（唯一活文档）

> **本文件是后端规格 + 运维的唯一入口。**  
> 历史草稿已移出 `docs/`（见仓库 `history/docs-archive/`），不再当作现行规格。  
> 前端产品文档不在本文件扩展；前后端分离，各自成产品。

---

## 目录

1. [项目定位](#1-项目定位后端视角)
2. [数据分层 L0–L2](#2-数据分层l0l2-后端--l3-前端)
3. [系统组成](#3-系统组成)
4. [核心域模型](#4-核心域模型摘要)
5. [HTTP API](#5-http-api-地图)
6. [鉴权](#6-鉴权模型)
7. [抓取与证据](#7-抓取与证据实现要点)
8. [前后端契约](#8-与前端的契约稳定约定)
9. [仓库边界](#9-仓库中的后端边界)
10. [状态](#10-版本与状态)
11. [运维环境](#11-运维环境一览)
12. [日常发布](#12-日常发布)
13. [鉴权与调试请求](#13-鉴权与调试请求)
14. [常用操作](#14-常用业务操作)
15. [Compose 变量](#15-compose-环境变量要点)
16. [故障速查](#16-故障速查)
17. [安全清单](#17-安全清单)
18. [Git 约定](#18-git-约定后端改动)

---

## 1. 项目定位（后端视角）

前后端分离，各自按**相对成熟的产品**设计：

| 侧 | 产品职责 |
|----|----------|
| **后端（本说明）** | 配置监测对象 → 抓取 AI 回答 → 结构化标注 → **只产出可审计的计数与明细** |
| **前端（另仓/另文档）** | 消费 API → 派生比率/图表 → 展示与下钻交互 |

**后端一句话：**  
对「品牌 × 问题库 × AI 平台」做可重复的可见性采集与计数，并提供配置/任务/明细/证据查询接口。

**后端不做：**

- 在 API 里返回「提及率 / SoV / 综合分」作为权威结果（比率属前端）
- 浏览器端 LLM 情感、内容生成、多租户计费
- 替代正式产品 UI（`/qa` 仅运维质检页）

---

## 2. 数据分层（L0–L2 后端 · L3 前端）

```text
L0 Raw        抓取产物：原文、平台、prompt、时间、截图路径、引用…
L1 Annotation 单次判定：answer_status、是否提及、mention_type、位置桶…
L2 Counts     聚合整数：n_valid、m_mentioned…（GET /v1/counts）
L3 Rates      前端：提及率 = m/n、SoV、综合分、趋势（本仓库不算）
```

| 层 | 权威落点 | 说明 |
|----|----------|------|
| L0 | `raw_responses` / `citations` + 截图文件 | 优先保留 DOM 原文；清洗字段可派生 |
| L1 | `raw_responses.answer_status` + `mentions` | 规则引擎，`annotator_version` 可重跑 |
| L2 | **实时 API 聚合**，非 `metric_snapshots` 表 | 表可存在但 **MVP 不当真相源** |
| L3 | 前端纯函数 | 只吃 counts + 配置 |

**分母：** 仅 `answer_status = ok` 计入 `n_valid`。  
**假数据：** counts 默认 `include_fake=false`（`source` 为 `fake*` 或正文 `【假数据` 排除）。

---

## 3. 系统组成

| 组件 | 路径/镜像 | 职责 |
|------|-----------|------|
| API | `apps/api` → `geo-api` | REST、鉴权、QA 页、静态托管预留 |
| Crawler | 同代码包 worker → `geo-crawler` | Playwright DeepSeek 真抓 / fake |
| DB | Postgres 16 → `geo-postgres` | 配置 + L0/L1 |
| 指标库 | `packages/metrics` | 别名匹配、位置桶等纯逻辑 + 单测 |
| 证据盘 | volume `/data/screenshots` | PNG 截图 |

**当前已实现平台：** DeepSeek Web（`deepseek_web`）。  
**登录态：** `DEEPSEEK_STORAGE_STATE`（JSON storage_state），禁止提交 Git。

---

## 4. 核心域模型（摘要）

| 表 | 用途 |
|----|------|
| `brands` / `brand_aliases` / `competitor_links` | 本品、别名、竞品图 |
| `prompts` | 监测提问（建议：正文**不出现**监测品牌名，避免提示污染） |
| `crawl_jobs` | 任务：pending → running → success/failed |
| `raw_responses` | L0 + `answer_status` / `annotator_version` |
| `mentions` | 每回答 × 每品牌一行（唯一约束） |
| `citations` | 引用链接（解析质量随平台而变） |

**L1 `answer_status`：** `ok` | `empty` | `too_short` | `error`  
（侧栏误抓、假数据标记等应进 `error`，不进分母。）

**L1 mention：** `mentioned`、`mention_type`（body / citation_only / none）、`position_bucket`（head / middle / tail）、可选 evidence。

---

## 5. HTTP API 地图

公网默认：`http://<host>:8200`。  
鉴权见 §6。完整字段以 OpenAPI（`/docs` 若开启）与代码 `apps/api/app/api/*` 为准。

### 5.1 配置

| 方法 | 路径 | 说明 |
|------|------|------|
| GET/POST | `/v1/brands` | 列表 / 创建 |
| GET/PATCH/DELETE | `/v1/brands/{id}` | 读改删（有子行时级联策略以代码为准） |
| GET/POST | `/v1/prompts` | 列表 / 创建 |
| GET/PATCH/DELETE | `/v1/prompts/{id}` | 读改删 |

### 5.2 采集

| 方法 | 路径 | 说明 |
|------|------|------|
| GET/POST | `/v1/crawl-jobs` | 列表 / 创建任务（`prompt_id` + `platform` + `samples`） |
| GET | `/v1/crawl-jobs/{id}` | 详情（可含 response） |
| POST | `/v1/crawl-jobs/{id}/retry` | 重试 |
| POST | `/v1/crawl-jobs/worker/run-once` | 手动踢 worker 一轮 |
| POST | `/v1/ingest/l0` | 外部灌入 L0（调试/桥接；非主路径） |

### 5.3 明细与标注

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/v1/responses` | 列表（过滤 brand/prompt/platform 等） |
| GET | `/v1/responses/{id}` | 详情：L0 + mentions + citations |
| POST | `/v1/responses/{id}/annotate` | 单条重标 |
| POST | `/v1/responses/annotate/run` | 批量重标 |

### 5.4 计数与口径（L2）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/v1/counts` | **只返回整数**；参数见下 |
| GET | `/v1/config/metrics` | 枚举、分母定义、默认综合分权重（供前端展示层） |

**`/v1/counts` 主要查询参数：**

- `brand_id`（必填）
- `platform` / `prompt_id` / `from` / `to`（`to` 按当日末闭合）
- `group_by`：`none` | `day` | `platform` | `prompt`
- `include_fake`：默认 `false`
- `source`：可选，如 `deepseek_web`

**返回要点：** `denominator.n_valid`、`brand.m_*`、`competitors[]`、`series[]`（分组时）。  
**禁止解读为比率权威：** `note` 字段会标明 counts only。

### 5.5 证据与运维页

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/v1/media/screenshots/{file}` | 截图文件 |
| GET | `/qa`、`/qa/jobs`、`/qa/responses`… | HTML 质检（非产品前端） |
| GET/POST | `/qa/login` | 下发读接口 Cookie |

### 5.6 健康

| 方法 | 路径 |
|------|------|
| GET | `/health`、`/health/db` |

---

## 6. 鉴权模型

| 通道 | 适用 |
|------|------|
| 请求头 `X-API-Key` 或 `Authorization: Bearer` | **任意方法** |
| HttpOnly Cookie `geo_qa_key`（`/qa/login` 下发） | **仅 GET / HEAD / OPTIONS** |

设计意图：

- 截图 `<img>` 无法带自定义头 → 读接口需要 Cookie  
- Cookie **不得**用于 POST/PATCH/DELETE → 降低 CSRF 写风险  

`API_KEY` 空 = 关闭鉴权（仅限本机）；**公网必须配置**（`deploy/.env`）。

---

## 7. 抓取与证据（实现要点）

1. Worker 领 `crawl_jobs` → Provider（`deepseek_web` / fake）  
2. L0：正文优先 DOM；流式拼接仅辅助  
3. 证据：抽取回答 HTML → 独立页渲染 → `full_page` 截图（避免侧栏污染）  
4. 可选：抓完删除 DeepSeek 会话，降低侧栏堆积  
5. 入库后跑 L1 标注 → 可供 `/v1/counts` 聚合  

失败任务：`error_message`；僵死 `running` 有回收逻辑（见代码/测试）。

---

## 8. 与前端的契约（稳定约定）

1. 指标展示 **只信任** `/v1/counts` 的整数再本地除法。  
2. 下钻用 `/v1/responses` + 截图 URL，不拼外部会话链接当证据。  
3. 写操作（建任务、改配置）必须带 API Key 头，不能只靠 Cookie。  
4. 平台未接入时不要假定 counts 有数据；当前生产主路径是 `deepseek`。  
5. 提问词 category 等归类：前端可读 `/v1/prompts`，**不要求** counts 增加 category 参数。

---

## 9. 仓库中的后端边界

```text
apps/api/           # FastAPI + worker 入口
apps/crawler/       # 历史/辅助（运行以 compose crawler 镜像为准）
packages/metrics/   # 纯逻辑
deploy/             # compose、Dockerfile、hook、init.sql
docs/BACKEND.md     # 本文件（规格）
docs/archive/       # 旧文档，不参与日常规格
apps/web/           # 前端占位；产品文档不由后端维护
```

---

## 10. 版本与状态（文档维护）

| 项 | 状态 |
|----|------|
| 配置 / 任务 / L0 / L1 / L2 / QA / 鉴权 / DeepSeek 真抓 | **已实现** |
| 第二 AI 平台 Provider | 未做 |
| 正式产品前端 | 前端侧负责 |
| LLM 情感 L1 | 后置，未做 |

变更 API 或口径时：**先改代码与测试，再改本文件**；不要再平行新增 `docs/28-*.md` 日记式规格。

---

# 运维部分

## 11. 运维环境一览

| 项 | 值 |
|----|-----|
| VPS | `96.9.213.230` |
| SSH 示例 | `ssh -i ~/Desktop/pem/SG-DC1.pem -o IdentitiesOnly=yes root@96.9.213.230` |
| 裸仓库 | `/opt/geo-demo.git` |
| 工作树 | `/opt/geo-demo` |
| Compose | `/opt/geo-demo/deploy` |
| 部署日志 | `/var/log/geo-demo-deploy.log` |
| API | `http://96.9.213.230:8200` |
| 容器 | `geo-api` · `geo-crawler` · `geo-postgres` |

**同机勿碰：** sillytavern `:8100`、fund-dashboard `:8090`、系统 nginx 80/443。

| 本服务端口 | 绑定 |
|------------|------|
| API | `0.0.0.0:8200`（公网，需 API Key） |
| Postgres | `127.0.0.1:5433` → 容器 5432 |
| 截图 | 容器内 `/data/screenshots`（volume） |

私钥、`deploy/.env`、`deepseek_storage.json`：**禁止 commit**。

---

## 12. 日常发布

```bash
# 本机仓库
cd /Users/xiagao/Desktop/geo-demo
git status
git add <files>
git commit -m "type(scope): 说明"
# 推荐：
export GIT_SSH_COMMAND='ssh -i /Users/xiagao/Desktop/pem/SG-DC1.pem -o IdentitiesOnly=yes'
git push vps main
# 或 ./scripts/push-vps.sh（若存在）
```

`post-receive` 会 checkout 工作树并 `docker compose build/up`（含 crawler 若已存在容器）。  
关注：`tail -f /var/log/geo-demo-deploy.log`。

**改 crawler/截图逻辑后确认镜像已重建：**

```bash
docker exec geo-crawler grep -n "关键符号" /app/apps/api/app/providers/deepseek_web.py | head
```

**DeepSeek 登录态（volume 丢失时）：**

```bash
# 本机导出 storage_state 后
docker cp deploy/deepseek_storage.json geo-crawler:/data/deepseek_storage.json
# 确保 compose 中 DEEPSEEK_STORAGE_STATE=/data/deepseek_storage.json
```

---

## 13. 鉴权与调试请求

```bash
# 读取 key（勿回显到聊天/文档）
ssh ... "grep '^API_KEY=' /opt/geo-demo/deploy/.env"

export KEY='...'   # 本地终端临时
curl -s -H "X-API-Key: $KEY" http://96.9.213.230:8200/health
curl -s -H "X-API-Key: $KEY" "http://96.9.213.230:8200/v1/counts?brand_id=34" | jq .
```

- **写接口**必须 Header Key  
- **QA 读页面：** 浏览器打开 `/qa/login` 提交 key → Cookie 后浏览 `/qa/responses`  
- Cookie **不能**代替 POST 建任务  

---

## 14. 常用业务操作

### 14.1 健康

```bash
curl -s http://127.0.0.1:8200/health          # VPS 上
curl -s -H "X-API-Key: $KEY" http://127.0.0.1:8200/health/db
docker ps --filter name=geo
```

### 14.2 触发抓取

```bash
curl -s -X POST http://127.0.0.1:8200/v1/crawl-jobs \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"prompt_id":<id>,"platform":"deepseek","samples":1}'
docker logs geo-crawler --since 5m 2>&1 | tail -50
```

### 14.3 计数与明细

```bash
curl -s -H "X-API-Key: $KEY" \
  "http://127.0.0.1:8200/v1/counts?brand_id=34&platform=deepseek"
curl -s -H "X-API-Key: $KEY" \
  "http://127.0.0.1:8200/v1/responses?limit=5"
```

### 14.4 数据脚本（API 容器内）

```bash
docker exec geo-api python -m app.scripts.verify_l2 --brand-id 34
docker exec geo-api python -m app.scripts.data_governance_min --dry-run
# 确认后再去掉 --dry-run
```

### 14.5 测试

```bash
# 本机（无 DB 集成项会 skip）
cd apps/api && PYTHONPATH=. pytest tests/ -q
cd packages/metrics && pytest -q

# VPS 全量（示例）
docker exec -w /app/apps/api -e PYTHONPATH=. \
  -e GEO_TEST_DATABASE_URL="postgresql+psycopg://geo:geo@postgres:5432/geo" \
  geo-api python -m pytest tests/ -q
```

---

## 15. Compose 环境变量要点

见仓库根 `.env.example` / `deploy` 环境：

| 变量 | 含义 |
|------|------|
| `DATABASE_URL` | API/crawler 连 Postgres |
| `API_KEY` | 公网鉴权 |
| `API_COOKIE_SECURE` | HTTPS 后 Cookie Secure |
| `CRAWL_MODE` | `real` / `fake` |
| `FAKE_WORKER_ENABLED` | API 内嵌假 worker；真抓时建议 `false` 防双领任务 |
| `DEEPSEEK_STORAGE_STATE` | storage_state 路径 |
| `SCREENSHOT_DIR` | 默认 `/data/screenshots` |
| `PLAYWRIGHT_HEADLESS` | 默认 true |
| `CRAWL_TIMEOUT_MS` | 抓取超时 |

生产真抓典型：`CRAWL_MODE=real`，`FAKE_WORKER_ENABLED=false`，crawler profile 开启。

---

## 16. 故障速查

| 现象 | 排查 |
|------|------|
| `missing or invalid API key` | 头未带 Key / `.env` 未进容器 |
| 任务一直 pending | `geo-crawler` 是否 Up；`CRAWL_MODE`；日志 |
| 登录墙 / 空答 | storage_state 是否有效；重新导出并 `docker cp` |
| 截图侧栏/输入框 | 是否旧镜像；日志有无 `clean-render`；重建 crawler |
| counts 命中异常 | 是否含 fake；`answer_status`；别名是否过宽（如裸 `361`） |
| push 后代码没变 | deploy 日志；容器是否 rebuild；worktree 与 image 是否一致 |
| running 僵死 | 查 jobs 表；依赖代码内回收；必要时 retry |

```bash
docker logs geo-api --since 30m 2>&1 | tail -80
docker logs geo-crawler --since 30m 2>&1 | tail -80
docker exec geo-postgres psql -U geo -d geo \
  -c "select id,status,error_message from crawl_jobs order by id desc limit 10;"
```

---

## 17. 安全清单

- [ ] `API_KEY` 已设且足够长  
- [ ] `.env`、`*.pem`、`deepseek_storage.json` 在 `.gitignore`  
- [ ] Postgres 仅 `127.0.0.1`  
- [ ] 不把 Key 写进前端仓库明文（写操作由用户/服务端保管）  
- [ ] 不在日志中打印 storage_state 全文  

---

## 18. Git 约定后端改动

```text
feat(api|crawl|metrics): 新能力
fix(api|crawl): 修 bug
docs: 仅文档
chore: 杂项/依赖
```

- 一步一 commit，说明写清「为什么」  
- push `main` 即部署；小心高峰时 rebuild crawler 耗时  
- 不在 commit 中夹带密钥与大体截图二进制  

---

## 19. 文档策略（本文件即终点）

| 路径 | 用途 |
|------|------|
| `docs/BACKEND.md` | 后端产品/规格（活文档） |
| `docs/BACKEND-RUNBOOK.md` | 本手册（活文档） |
| `docs/archive/*` | 历史 B 步、L3 草案、踩坑长文 — **默认不更新** |

前端产品说明不放本目录扩写；对接只引用 `BACKEND.md` §5–§8。
