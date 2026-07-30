# 前后端设计架构（详细版）

> 项目定位：个人学习 / 本地与 VPS 可部署的 GEO 投流分析系统  
> 关联文档：[MVP 范围](./01-mvp-scope.md) · [数据模型](./02-data-model.md) · [指标规格](./03-metrics-spec.md) · [开源评估](../%23%20开源项目评估（可用于GEO系统）.md) · [头脑风暴](../%23%20GEO投流分析系统%20全栈构建头脑风暴（第一版）.md)  
> 实施约定：**先后端、后前端**；后端再拆成可验收的小步，每步由你确认后再做。

---

## 1. 文档目的与阅读方式

本文回答三件事：

1. **系统怎么分层**（数据从哪来、怎么算、怎么展示）  
2. **前后端各自负责什么、边界在哪**  
3. **每一层可对照哪些竞品 / 开源**（引用写在对应模块旁，便于实现时回看）

**不是**实现任务单，也**不**代替你拍板技术细节；文中「建议」仅作学习向默认方案，最终以你确认的步骤为准。

---

## 2. 产品能力地图（前后端共同对齐）

核心价值（来自头脑风暴）：把「AI 回答里有没有提到我、怎么提、引用了谁、情感如何、和竞品比怎样」变成可量化数据。

```text
┌─────────────┐   ┌──────────────┐   ┌─────────────┐   ┌──────────────┐
│ 配置域       │ → │ 采集域        │ → │ L1 轻结构    │ → │ 呈现 + L2 派生 │
│ 品牌/竞品    │   │ 任务/抓取     │   │ 命中/位置    │   │ 看板/钻取/指标 │
│ Prompt 库    │   │ 原文/引用/证据 │   │ （后端）     │   │ （前端为主）   │
└─────────────┘   └──────────────┘   └─────────────┘   └────────────────┘
     后端为主              后端为主            后端               前端为主
```

| 能力域 | 用户可感知结果 | 主责 |
|--------|----------------|------|
| 配置 | 管品牌、别名、竞品、问题库 | 后端 API + 前端表单 |
| 采集 | 对某 Prompt×平台跑任务，看到成功/失败 | 后端 Worker + 队列 |
| 分析（L1） | 命中别名、首次位置等轻结构化 | **后端**入库时写入（质检 + 减前端压力） |
| 分析（L2） | 提及率、SoV、综合分、趋势 | **前端派生**为主；后端不强制聚合 Job |
| 呈现 | 总览、对比、点进看原文 | 前端；读 raw + L1 |

### 2.1 竞品能力对标（产品层）

| 能力 | 竞品参考 | 我们 MVP 目标 | 引用说明 |
|------|----------|---------------|----------|
| 品牌监测 / 提及追踪 | [g1geo 极义GEO](https://g1geo.com/)：品牌监测、实时 AI 对话、提及与引用 | 品牌+别名+竞品；按 Prompt 采样后的提及与引用入库 | 头脑风暴 §2 对标对象；功能齐但闭源，只对标**产品能力**不抄实现 |
| 全平台覆盖 | g1geo 宣称 DeepSeek / 豆包 / 元宝 / 千问 / 文心 / Kimi 等 | MVP：DeepSeek → 豆包 →（可选）Kimi/通义 | 平台列表对齐国内主流，范围见 [01-mvp-scope](./01-mvp-scope.md) |
| 内容优化 / 报告 | g1geo 内容建议、增长报告 | **学习版不做**报告中心与内容生成 | 进阶能力，避免 MVP 膨胀 |
| 免费检测入口 | g1geo 落地页检测 | 学习版可不做公网落地页 | 增长手段，非核心架构 |
| 海外 AEO 产品形态 | [Elmo 产品站](https://www.elmohq.com/) / [demo](https://demo.elmohq.com)：prompt 追踪、citation、竞品 | 呈现域信息架构可参考「Prompt → 回答 → 引用」钻取 | 开源实现见 §5.4 / §7 的 elmo 仓库 |
| 可见性分数叙事 | Otterly / AthenaHQ 等（开源近似：[ai-visibility](https://github.com/sharozdawa/ai-visibility) 的权重表述） | 可解释分 = 提及 + 位置 + 情感（权重可配） | 公式见 [03-metrics-spec](./03-metrics-spec.md) |

> 竞品用于**能力清单与交互预期**；数据真实性、抓取方式以我们自建为准。

---

## 3. 逻辑架构总图

```text
                    ┌──────────────────────────────────────────┐
                    │              Web (Frontend)               │
                    │  看板 · Prompt 浏览器 · 设置 · 竞品对比     │
                    └─────────────────┬────────────────────────┘
                                      │ HTTPS / JSON REST
                    ┌─────────────────▼────────────────────────┐
                    │           API Service (Backend)           │
                    │  配置 CRUD · 任务下发 · 查询聚合 · 分析试算 │
                    └───────┬─────────────────┬────────────────┘
                            │                 │
              ┌─────────────▼──────┐   ┌──────▼──────────────┐
              │  PostgreSQL         │   │  Redis              │
              │  元数据+原文+指标    │   │  队列 / 缓存(可选)   │
              └─────────────▲──────┘   └──────┬──────────────┘
                            │                 │ 取任务
              ┌─────────────┴─────────────────▼──────────────┐
              │           Crawler Worker (Backend)            │
              │  Provider(平台) → 原文/截图 → 解析 → 指标写入   │
              └─────────────┬────────────────────────────────┘
                            │ Playwright
              ┌─────────────▼────────────────────────────────┐
              │   AI Web UI（DeepSeek / 豆包 / …）              │
              └──────────────────────────────────────────────┘

旁路包：
  packages/metrics  —— 纯函数指标（API 试算 & Worker 落库共用）
```

**同步请求路径（前端 → API → DB）**  
读看板、改品牌/Prompt、查某次回答全文。

**异步任务路径（API → 队列 → Worker → 平台 → DB）**  
创建抓取任务、定时调度、批量 Prompt。

**设计原则**

| 原则 | 含义 |
|------|------|
| 前后端分离 | 前端不直连数据库、不内嵌抓取 |
| 采集与查询分离 | Worker 可独立扩缩/重启，不影响读 API |
| 指标分层 | **L0 原文 / L1 轻结构后端；L2 看板指标前端派生**（见 §4.4） |
| 证据可钻取 | 凡看板数字应能回到 `raw_responses` 全文（及可选截图） |
| 平台可插拔 | `BaseProvider` + 每平台一个实现，改版只动 Provider |
| 前端减负 | L1 入库时算好命中，避免看板每次全量扫全文 |

---

## 4. 后端架构（本阶段重点）

### 4.1 后端进程划分

| 进程 | 职责 | 不负责 |
|------|------|--------|
| **api** | REST、参数校验、编排「创建任务」、只读聚合查询、同步试算分析 | 长时间 Playwright、浏览器生命周期 |
| **worker** | 消费抓取任务、调 Provider、写 raw/citation、**L1 轻结构 mention** | 看板级 SoV/趋势聚合（前端做） |
| **postgres** | 持久化 | — |
| **redis** | 任务队列（及可选缓存） | 作为唯一业务库 |

> 学习版可先把 worker 做成「API 进程内的后台线程/子命令」，但**逻辑边界**仍按上表切分，便于以后拆进程。  
> 开源对照：  
> - [elmohq/elmo](https://github.com/elmohq/elmo) — `apps/web` + `apps/worker` + 队列（pg-boss）的**进程分工**  
> - [xxxbozzz/gitgeo](https://github.com/xxxbozzz/gitgeo) — FastAPI 路由分层 + Compose 本地栈  
> - [AI2HU/gego](https://github.com/AI2HU/gego) — scheduler 与 worker 分离、品牌别名与引用统计（**GPL-3，只学结构不引进依赖**）

### 4.2 后端分层（api 进程内部）

```text
app/
  api/           # 路由：HTTP 入参出参，无业务公式
  schemas/       # Pydantic 请求/响应
  services/      # 用例：创建品牌、提交抓取、查询看板
  models/        # ORM ↔ 表（见 02-data-model）
  core/          # 配置、DB session、队列客户端
```

| 层 | 允许 | 禁止 |
|----|------|------|
| api | 调 service、返回 schema | 写 SQL、调 Playwright |
| services | 事务、调仓库、投递队列、调 metrics | 依赖 FastAPI Request 细节 |
| models | 表映射 | 指标公式 |
| metrics 包 | 纯函数 | IO、HTTP、DB |

开源对照：[gitgeo](https://github.com/xxxbozzz/gitgeo) 的 `backend/app/{api,services,repositories}` 组织方式。

### 4.3 采集子系统（worker + providers）

```text
CrawlJob(pending)
    → Worker 领取
    → Provider.search(prompt)
         ├─ 启动/复用 Browser 上下文（登录态目录）
         ├─ 打开平台 Web
         ├─ 输入 Prompt、等待生成结束
         ├─ 优先：拦截 XHR/API 响应拿正文与引用
         └─ 回落：DOM 抽取正文
    → 规范化 CrawlResult{ full_text, citations, raw_json, screenshot? }
    → 持久化 raw_responses + citations
    → 对 本品+竞品 跑 metrics → mentions
    → 更新 job status
    →（可选）重算 metric_snapshots
```

| 模块 | 说明 | 开源 / 资料引用 |
|------|------|----------------|
| **Provider 接口** | `search(prompt) -> CrawlResult` | [geo_marketing `BaseProvider`](https://github.com/daijinma/geo_marketing) 的返回形态思路（**无 License，只对照不粘贴**） |
| **DeepSeek Web** | 第一实现；网络拦截 completion + 引用 | 同仓 `providers/deepseek_web.py` 模式：拦截优先 |
| **豆包 Web** | 第二实现 | 同仓 `doubao_web.py`；[gitgeo probe 配置](https://github.com/xxxbozzz/gitgeo) 的 URL/选择器表结构 |
| **多平台配置表** | platform → url / 选择器 / 设备 | [gitgeo `core/probe`](https://github.com/xxxbozzz/gitgeo) platform×device |
| **反检测方向** | 学习版可先普通 Playwright；进阶 CloakBrowser | gitgeo 使用 CloakBrowser 的路线（可选） |
| **引用/域名** | url → domain → 类型粗分 | geo_marketing `parser` 的域名分类思路 |
| **海外 Provider（后期）** | 官方 API 或付费 scrape | [elmo providers](https://github.com/elmohq/elmo)（oxylabs/brightdata/openai-api 注册表）；[aeo-platform providers](https://github.com/webappski/aeo-platform)；[oxylabs/chatgpt-scraper](https://github.com/oxylabs/chatgpt-scraper) 等 **SDK 示例** |
| **非真实监测（勿当采集实现）** | 仿真回答 | [GEO-Insight](https://github.com/huanghfzhufeng/GEO-Insight) 为 Bocha+Jina+LLM **模拟**，可借鉴 Judge 字段，**不能**替代 Web 抓取 |

**采集可靠性（架构预留，实现可分步）**

- 任务状态机：`pending → running → success | failed`  
- 重试：网络/超时有限次；登录失效单独错误码  
- 超时与并发：单机限制并行 browser 数  
- 证据：`full_text` 必填；`screenshot_path` / `raw_json` 可选  

### 4.4 数据与指标分层（2026-07-30 修订）

```text
L0 原始（后端必存）
  full_text, citations[], platform, prompt_text, created_at, screenshot_path?

L1 轻结构化（后端写入，服务质检 + 减前端压力）
  mentioned / mention_type / first offset → position_bucket
  （可选）evidence_snippet；本品+竞品各一行 mention

L2 看板指标（前端派生，主路径）
  visibility_rate, SoV, composite_score, 趋势序列, 平台对比图
```

| 层级 | 谁 | 存储 / 接口 |
|------|----|-------------|
| L0 | Worker | `raw_responses` + `citations` |
| L1 | Worker（可用 `packages/metrics` 纯函数） | `mentions` 表；B7 质量页直接读 |
| L2 | **前端** | 浏览器内聚合；**不强制** `metric_snapshots` / `/v1/.../metrics` |

`packages/metrics`：保留，用于 L1、可选 `/v1/analyze/*` 试算、算法对照；**不是**看板唯一权威服务。

算法对照仍见 [03-metrics-spec](./03-metrics-spec.md) 与 aeo-platform / GEO-Insight judge 字段思路。

**前端约定**：L2 公式建议与 `packages/metrics` / 规格文档对齐，避免魔法数；但运行时以前端实现为准（学习分工）。

### 4.5 数据存储架构

| 存储 | 存什么 | 为何 |
|------|--------|------|
| **PostgreSQL** | brands、prompts、jobs、raw_responses、mentions、citations、metric_snapshots | 学习版单一真相来源，事务简单 |
| **Redis** | 队列（如 RQ/Arq/Celery broker） | 异步解耦 |
| **本地目录 / 以后 MinIO** | 截图、可选 HTML | MVP 可用 `./data/screenshots` |

表结构详见 [02-data-model](./02-data-model.md)；初始化草稿：`deploy/init.sql`。

**刻意不做（MVP）**：独立 ES/ClickHouse/时序库——等数据量和查询模式需要再拆（头脑风暴 §5 的进阶存储）。

开源对照：

- geo_marketing `geo_db`：`search_records` + `citations` 分表思路  
- gitgeo：PostgreSQL + SQLAlchemy async  
- elmo：PostgreSQL + 迁移体系（SaaS 级，后期再学）  
- gego：PG 配配置 + Mongo 存回答（我们 MVP **不采用**双库，降低复杂度）

### 4.6 后端 API 域划分（REST 草图）

> 路径名为建议，实现前可再定版；此处用于前后端契约对齐。

#### 配置域

| 方法 | 路径 | 说明 |
|------|------|------|
| GET/POST | `/v1/brands` | 列表 / 创建 |
| GET/PATCH/DELETE | `/v1/brands/{id}` | 详情 / 更新 / 删除 |
| PUT | `/v1/brands/{id}/aliases` | 别名全量更新 |
| PUT | `/v1/brands/{id}/competitors` | 竞品 id 列表 |
| GET/POST | `/v1/prompts` | 支持 `brand_id` 过滤 |
| PATCH/DELETE | `/v1/prompts/{id}` | |

#### 采集域

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/v1/crawl-jobs` | body: `prompt_id` / `platform` / `samples` → 入队 |
| GET | `/v1/crawl-jobs` | 过滤 status/platform |
| GET | `/v1/crawl-jobs/{id}` | 状态 + 关联 response 摘要 |
| POST | `/v1/crawl-jobs/{id}/retry` | 失败重试 |

#### 查询 / 分析域

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/v1/responses/{id}` | **L0+L1**：全文 + citations + mentions（钻取） |
| GET | `/v1/responses` | 按 brand/prompt/platform/时间过滤列表（供前端拉样做 L2） |
| GET | `/v1/brands/{id}/metrics` | **可选 / MVP 可砍**（L2 改前端） |
| GET | `/v1/brands/{id}/compare` | **可选 / MVP 可砍** |
| POST | `/v1/analyze/response` | 同步 L1 试算（已有骨架，不入库） |
| GET | `/health` | 探活 |

前端看板依赖：**配置域 + 采集状态 + 查询域（L0/L1）**；L2 在前端算。触发监测走采集域。

### 4.7 后端推荐技术栈（学习默认，可改）

| 组件 | 默认建议 | 备选 | 参考来源 |
|------|----------|------|----------|
| API 框架 | FastAPI | — | gitgeo；头脑风暴 §7 |
| ORM | SQLAlchemy 2 async | 同步 SQLAlchemy | gitgeo |
| 校验 | Pydantic v2 | — | FastAPI 标配 |
| 队列 | Redis + Arq 或 RQ | Celery（更重） | 头脑风暴 Celery；elmo 用 pg-boss（TS 栈） |
| 抓取 | Playwright Python | CloakBrowser（进阶） | geo_marketing / gitgeo |
| 指标 | 自研 `packages/metrics` | — | aeo-platform 公式对照 |
| 配置 | `.env` + pydantic-settings | — | 常见做法 |
| 部署 | docker-compose | 本地 venv 分进程 | gitgeo compose；elmo compose |

### 4.8 后端实施步骤（供你逐步勾选，**未授权不执行**）

下列顺序是架构依赖上的合理拆分，**每步需你明确说做哪一步**：

| 步骤 | 名称 | 交付物 | 验收标准（建议） |
|------|------|--------|------------------|
| **B0** | 架构与契约冻结 | 本文 + 你确认的 API/表差异 | 你点头「按此做后端」 |
| **B1** | DB 落地 | 迁移/init 与连接配置 | compose 起 PG，表存在 |
| **B2** | 配置域 API | brands / aliases / competitors / prompts CRUD | curl/httpie 可走通 |
| **B3** | 任务模型 + 假 Worker | crawl_jobs 入队；worker 写一条假 raw_response | 不打开浏览器也能跑通状态机 |
| **B4** | **L1 轻结构化落库**（原 metrics 步骤降级） | 假文本或抓取结果 → `mentions`（命中/位置）；**不做**看板 snapshot 强依赖 | 库中可见 L1 mention |
| **B5** | DeepSeek Provider POC | 真抓 1 条 Prompt | success + **full_text** 非空（+ 尽量 citations） |
| **B6** | 查询域 API（L0/L1） | responses 列表/详情、按条件过滤；**聚合 metrics 可选砍** | 前端能拉齐做 L2 与钻取 |
| **B7** | **后端数据可视化（质量预览）** | 简易页：jobs / raw_responses / L1 mentions | 不接正式前端也能看抓取质量 |
| **B7+** | 第二平台 / 定时 / 截图 | 按你优先级插入 | 另定 |

**当前进度锚点**：metrics 包与 analyze 试算骨架已有；**B1 起未正式按上表推进**。  
下一步默认等待你指定：例如「做 B1」或「先改架构某节」。

---

## 5. 前端架构（先设计、后实施）

> 后端未到 B6 前，前端可只做静态壳，但**不作为当前执行重点**。

### 5.1 前端职责

| 做 | 不做 |
|----|------|
| 路由与布局、图表、表格、表单 | 抓取、直连 PG |
| 调用 REST 取 L0/L1，**派生 L2 指标**并可视化 | 浏览器自动化 |
| 下钻到原文抽屉/详情页 | 另起一套与 L0 对不上的「黑盒分」却不提供钻取 |

### 5.2 页面信息架构

```text
/                    总览仪表盘
/brands              品牌列表
/brands/:id          品牌详情（别名、竞品、快捷指标）
/prompts             Prompt 库（筛选品牌/标签）
/prompts/:id         Prompt 详情（历史回答、分平台）
/jobs                抓取任务列表
/responses/:id       单次回答证据（全文、引用、提及高亮）
/compare             竞品对比
/settings            平台、抓取参数等
```

| 页面 | 关键组件 | 产品/开源对照 |
|------|----------|----------------|
| 总览 | KPI 卡片、趋势折线、平台分布 | g1geo 增长/监测看板预期；[GEO-Insight 前端 dashboard 组件划分](https://github.com/huanghfzhufeng/GEO-Insight) |
| Prompt 浏览器 | 表 + 抽屉原文 | elmo demo 的 prompt→回答路径；aeo-platform 报告中的 per-query 视角 |
| 竞品对比 | 并列柱/雷达 | g1geo 对比能力；ai-visibility `compare_brands` 能力描述 |
| 任务列表 | 状态徽章、重试 | geo_marketing 桌面端任务管理思路 |
| 设置 | 品牌/平台 | deepseek-geo 管理台菜单 IA（[DeepSeekGEO/deepseek-geo](https://github.com/DeepSeekGEO/deepseek-geo) **仅前端壳**） |

### 5.3 前端技术建议（默认，实施前再确认）

| 项 | 建议 | 参考 |
|----|------|------|
| 框架 | Next.js（App Router）+ TypeScript | 头脑风暴 §6；gitgeo 管理端也是 Next |
| UI | Tailwind + shadcn/ui | geo_marketing client 使用同类栈 |
| 图表 | ECharts 或 Recharts | 头脑风暴 §6 |
| 数据获取 | fetch/SWR 或 TanStack Query | 标准 React 数据层 |
| API 类型 | 手写 DTO 或 OpenAPI 生成 | 后端可用 FastAPI 导出 OpenAPI |

### 5.4 前端与后端契约原则

1. 列表接口支持分页与过滤（`brand_id`、`platform`、`from`/`to`）。  
2. 指标接口返回**已计算字段** + `sample_size` + 时间窗，便于展示置信度。  
3. 钻取：`metric → 可列出 contributing response ids`（MVP 可先人工按 prompt/platform 查）。  
4. 错误：统一 `{ "detail": "..." }` 或 `{ "error": { code, message } }`（实现时定一种）。

开源对照：elmo 强调指标可审计、自托管；我们用「原文钻取」落实同一理念。

### 5.5 前端实施步骤（预告，不动工）

| 步骤 | 名称 | 依赖后端 |
|------|------|----------|
| F1 | 布局 + 路由空壳 | 无 |
| F2 | 品牌/Prompt 配置页 | B2 |
| F3 | 任务触发与列表 | B3+ |
| F4 | 总览 + 趋势（**前端 L2 派生**） | B6（有 L0/L1 即可） |
| F5 | 原文钻取 + 竞品对比 | B6 |

---

## 6. 端到端时序（便于联调想象）

### 6.1 配置并抓取一次

```text
用户(前端)          API                Redis/Queue         Worker              AI Web
   │ 建品牌/Prompt    │                    │                  │                  │
   │─────────────────>│ 写 PG              │                  │                  │
   │ 点「监测」        │                    │                  │                  │
   │─────────────────>│ 建 crawl_job       │                  │                  │
   │                  │ 入队 ─────────────>│                  │                  │
   │<──── job_id ─────│                    │                  │                  │
   │                  │                    │  pop ───────────>│                  │
   │                  │                    │                  │  Playwright ────>│
   │                  │                    │                  │<── 回答/引用 ────│
   │                  │                    │                  │ metrics + 写 PG  │
   │ 轮询/刷新 job     │                    │                  │                  │
   │─────────────────>│ 读 job+response    │                  │                  │
   │<──── success ────│                    │                  │                  │
```

### 6.2 看板读取

```text
前端 GET /brands/{id}/metrics?from&to&platform
  → API 读 metric_snapshots 或即时聚合 mentions
  → 返回 series + KPI
前端点击某点/某 Prompt
  → GET responses 或 GET prompts/{id} 历史
  → 展示 full_text + 高亮别名
```

---

## 7. 外部参考索引（按类型汇总）

### 7.1 竞品 / 产品（能力与 UX）

| 名称 | 链接 | 架构文档中的用途 |
|------|------|------------------|
| 极义 GEO (g1geo) | https://g1geo.com/ | 主对标：监测、平台覆盖、报告类能力边界 |
| Elmo 产品/Demo | https://www.elmohq.com/ · https://demo.elmohq.com | Prompt 追踪与 citation 钻取体验 |
| 超算 GEO 官网 | https://chaosuangeo.com/ （开源仓仅为前端） | 管理台业务模块广度（监控/内容/合规） |

### 7.2 开源仓库（实现对照）

| 仓库 | 链接 | 主要引用位置 |
|------|------|--------------|
| daijinma/geo_marketing | https://github.com/daijinma/geo_marketing | §4.3 抓取 Provider、拦截、引用解析（无 License，只学） |
| xxxbozzz/gitgeo | https://github.com/xxxbozzz/gitgeo | §4.1–4.3 API 分层、probe 配置、Compose |
| elmohq/elmo | https://github.com/elmohq/elmo | §4.1 worker 分工、§5 产品化前端、Provider 注册表 |
| webappski/aeo-platform | https://github.com/webappski/aeo-platform | §4.4 提及/多采样/可见性算法 |
| huanghfzhufeng/GEO-Insight | https://github.com/huanghfzhufeng/GEO-Insight | §4.4 Judge 字段；§5 dashboard 划分；**非真抓取** |
| DeepSeekGEO/deepseek-geo | https://github.com/DeepSeekGEO/deepseek-geo | §5.2 后台 IA；无监测后端 |
| AI2HU/gego | https://github.com/AI2HU/gego | §4.1 调度思路；GPL-3 不引进 |
| sharozdawa/ai-visibility | https://github.com/sharozdawa/ai-visibility | §2.1 / §4.4 分数权重叙事；数据模拟 |
| LLM-X-Factorer/awesome-geo-cn | https://github.com/LLM-X-Factorer/awesome-geo-cn | 中文 GEO 资源跟踪 |
| oxylabs/chatgpt-scraper 等 | https://github.com/oxylabs/chatgpt-scraper | §4.3 海外付费 scrape 插件化（后期） |

更细的星数/License/是否真抓取见仓库根目录 [开源项目评估](../%23%20开源项目评估（可用于GEO系统）.md)。

### 7.3 本仓库已有实现锚点

| 路径 | 对应架构 |
|------|----------|
| `packages/metrics` | §4.4 分析子系统 |
| `apps/api/app/main.py` | §4.6 中 analyze + health 雏形 |
| `apps/crawler/providers` | §4.3 Provider 桩 |
| `deploy/init.sql` | §4.5 表结构草稿 |
| `docs/01–03` | 范围、模型、指标 |

---

## 8. 与 monorepo 目录的映射

```text
geo-demo/
├── apps/
│   ├── api/          → 后端 API 进程（§4.2）
│   ├── crawler/      → 后端 Worker / Provider（§4.3）
│   └── web/          → 前端（§5，后置）
├── packages/
│   └── metrics/      → 分析核心库（§4.4）
├── deploy/           → PG/Redis/compose（§4.5）
└── docs/
    ├── 01-mvp-scope.md
    ├── 02-data-model.md
    ├── 03-metrics-spec.md
    └── 04-architecture.md  ← 本文
```

---

## 9. 风险与架构对策（简表）

| 风险 | 对策（架构层） |
|------|----------------|
| 平台改版导致选择器失效 | Provider 隔离；拦截 API 优先于 DOM；失败状态可观测 |
| 回答随机性 | 多采样字段 `sample_index` + sampling 聚合（规格 §3） |
| 指标前后端不一致 | 唯一实现于 `packages/metrics` |
| 学习项目复杂度爆炸 | 单 PG、单 workspace、先假 Worker 再真抓取（§4.8） |
| 误用仿真项目当真监测 | 文档与评估明确 GEO-Insight / ai-visibility 边界 |

---

## 10. 已确认事项（2026-07-30）

1. **后端步骤**：认可 B0→B7；从 **B1** 开工。  
2. **API 风格**：REST 草图可先按 §4.6 落地，有问题再改。  
3. **队列**：B3 阶段再定（Redis vs DB 轮询）；B1 不涉及。  
4. **前端**：等后端 **B6** 后；插入 **B7 后端数据可视化** 看抓取质量，再做正式前端。  
5. **开源**：实现时按需对照，减少重复劳动（遵守各仓 License/学习边界）。  
6. **Git**：先建规范再提交推进。  

---

## 10.1 运行环境变更（2026-07-30）

- 本机 Docker 不可用 → **不在本地做运行时测试**。
- 代码本地编写 → `git push vps` → VPS（`96.9.213.230`）Docker 运行。
- 详见 [08-vps-deploy](./08-vps-deploy.md)。

## 修订记录

| 日期 | 说明 |
|------|------|
| 2026-07-30 | 初版：前后端详细架构 + 竞品/开源引用挂载到模块 + 后端分步 B0–B7 |
| 2026-07-30 | **路线确认**：Git 规范后开工；先 B1；前端等后端 B6 后；**B7=后端数据可视化看抓取质量**，再做前端；需要时对照开源减负 |
| 2026-07-30 | **数据职责折中**：L0/L1 后端，L2 前端派生；减轻前端全量扫文压力；B4/B6 metrics 聚合降级 |
