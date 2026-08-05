# GEO Demo · 后端产品说明

> **角色：** 本仓库后端（`apps/api` + crawler + `packages/metrics`）  
> **读者：** 后端维护者、对接前端的人  
> **前端文档：** 由前端工程自行维护，不在此堆叠  
> **运维命令：** 见 [BACKEND-RUNBOOK.md](./BACKEND-RUNBOOK.md)  
> **历史草稿/验收日记：** `docs/archive/`（只读归档，不再当规格）

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
docs/BACKEND-RUNBOOK.md
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
