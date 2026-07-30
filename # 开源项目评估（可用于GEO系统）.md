# GEO 相关开源项目评估（代码级审查）

> 审查日期：2026-07-29  
> 方法：GitHub metadata + shallow clone + README/源码结构核对  
> 目标：判断哪些可直接用、哪些只参考、哪些应避开  
> **项目定位：个人学习项目（非商用）**

---

## 总览结论

| 优先级 | 项目 | 对我们的价值 | 建议用法 |
|--------|------|--------------|----------|
| **P0 必学** | `daijinma/geo_marketing` | 国内 **真实 Web 抓取**（DeepSeek/豆包）最完整 | **重写借鉴**，不要 fork（无 License） |
| **P0 必学** | `xxxbozzz/gitgeo` | MIT + FastAPI/Next/PG + 国内 4 平台探测 + CloakBrowser | 技术栈与探测层 **强烈参考** |
| **P0 必学** | `elmohq/elmo` | 最成熟的 **SaaS monorepo 架构**（worker/队列/provider 抽象） | 架构蓝本；海外模型为主 |
| **P1 指标** | `webappski/aeo-platform` | 纯函数指标库：mention / multi-sample / visibility index | **直接移植指标算法**（MIT） |
| **P1 UI/IA** | `DeepSeekGEO/deepseek-geo` | 完整管理台页面结构（监控/内容/合规） | 只抄信息架构，后端是闭源 SaaS |
| **P2 评分** | `huanghfzhufeng/GEO-Insight` | Judge Prompt、多智能体评分 JSON schema | 只学评分逻辑；**不是真实平台可见性** |
| **P2 架构** | `AI2HU/gego` | Go 调度/品牌别名/引用统计/仪表盘 | 思路参考；**GPL-3 商用有传染风险** |
| **P3 演示** | `sharozdawa/ai-visibility` | 可见性分数公式、MCP、Next 壳 | 分数权重可参考；**数据是模拟的** |
| **可选付费** | oxylabs / brightdata 类 | 海外 ChatGPT/Perplexity 抓取 | 作 Provider 插件，不当核心依赖 |
| **列表** | `awesome-geo-cn` | 资源索引 | 持续关注即可 |

**一句话**：我们自己建系统；从开源 **拆零件**（抓取模式、指标公式、SaaS 架构），不要指望整仓 fork。

---

## 分项目详评

### 1. LLM Sentry / `daijinma/geo_marketing` ⭐ 国内抓取第一参考

| 项 | 内容 |
|----|------|
| Stars | ~71 |
| License | **无**（商用/复制有法律风险） |
| 语言 | Python Playwright + Go/React(Wails) 桌面端 |
| 平台 | DeepSeek、豆包（Web） |

**真实能力（已核代码）**
- `providers/deepseek_web.py` / `doubao_web.py`：Playwright 真打开网页
- **网络响应拦截**拿 completion 与搜索引用（比纯 DOM 稳）
- `core/parser.py`：域名提取、站点类型分类（知乎/自媒体/新闻）
- `stats.py`：SoV、引用源、jieba 分词洞察
- `geo_db/init.sql`：`search_records` / `citations` 等表
- 桌面端 `geo_client2`：任务管理、登录态、本地 SQLite

**可复用**
- Provider 抽象：`BaseProvider.search() -> {full_text, citations}`
- 拦截 API 响应 + 回落 DOM 的双路径
- 引用解析与域名分类规则
- 本地登录态目录（browser user_data_dir）模式

**不可直接用**
- 无 License → 不要整段 copy 进闭源/商用仓
- 反爬/代理/账号池仍偏弱
- 只有 2 个平台

**建议**：自己重写同构 Provider；对照其选择器与拦截 URL 模式做 POC。

---

### 2. `xxxbozzz/gitgeo` ⭐ 全栈国内工作流 + MIT

| 项 | 内容 |
|----|------|
| Stars | ~18 |
| License | **MIT** |
| 栈 | FastAPI + Next.js 14 + PostgreSQL + CloakBrowser |
| 平台 | DeepSeek / 豆包 / Kimi / 元宝（桌面+移动） |

**真实能力**
- `core/probe/`：统一探测层，配置 URL/选择器/设备画像
- CloakBrowser（反检测 Playwright）用于探测与发布
- 完整 GEO 内容闭环（关键词→生成→质检→探测→反馈→发布）
- 管理后台、Docker Compose、pytest

**可复用（高）**
- **技术栈几乎可直接对齐**我们的目标栈
- Probe 配置表结构（platform × device）
- `analyzers` 可见性摘要逻辑
- FastAPI 路由分层 + SQLAlchemy async 组织方式

**注意**
- 探测选择器会随平台改版失效，需当「起点」维护
- 项目偏「内容生产 + 探测闭环」，不是纯投流分析 SaaS
- 体量不大（probe ~400 行），成熟度中等

**建议**：作为 **国内探测层 + monorepo 工程模板** 的首选 MIT 参考。

---

### 3. `elmohq/elmo` ⭐ 最接近产品级的开源 AEO/GEO SaaS

| 项 | 内容 |
|----|------|
| Stars | ~208（清单里最强） |
| License | **MIT** |
| 栈 | TypeScript monorepo、TanStack Start、PostgreSQL、pg-boss、Docker |
| 数据源 | 官方 API + 第三方抓取 Provider（Oxylabs / Bright Data / DataForSEO / Olostep） |

**真实能力**
- `apps/web` + `apps/worker` + `apps/cli` 完整分工
- Provider 注册表抽象（可插拔 scrape vs API）
- 品牌 onboarding、prompt 追踪、citation 分析
- 自托管 + 白标包

**可复用（架构级）**
- monorepo 边界：web / worker / lib / config
- **Provider 接口设计**（isConfigured / scrape / models）
- 任务队列与 worker 模式
- 指标可审计、数据自托管的产品叙事

**不匹配处**
- 主战场是 **海外模型**（ChatGPT/Claude/Perplexity/Gemini）
- 国内豆包/DeepSeek Web 抓取 **不是它的强项**
- 重度依赖付费 scrape 供应商时成本高

**建议**：SaaS 架构与产品信息架构照着学；国内抓取仍走自建 Playwright。

---

### 4. `webappski/aeo-platform` ⭐ 指标算法宝库（MIT、零依赖倾向）

| 项 | 内容 |
|----|------|
| License | MIT |
| 形态 | Node CLI，官方 API 调 ChatGPT/Claude/Gemini/Perplexity |

**可直接移植的纯逻辑**
- `lib/mention.js` / `lib/brand-match.js`：提及判定
- `lib/sampling.js`：多采样聚合（yes/src/no，presence rate）
- `lib/report/visibility-index.js`：可见性指数
- 情感、引用分类、竞品抽取、报告导出等

**建议**：把指标层做成我们自己的 `packages/metrics`（Python 或 TS 重写并单测），**这是性价比最高的代码复用点**。

---

### 5. `DeepSeekGEO/deepseek-geo`（超算GEO）— 前端壳

| 项 | 内容 |
|----|------|
| License | MIT（基于 vue-element-admin） |
| 实质 | **仅管理平台前端**，后端指向外部 `VUE_APP_BASE_API` |

**可复用**
- 页面信息架构：监控看板、合规检测、内容生成、发布、竞品等菜单
- Vue/Element 后台布局模式（若我们用 React 则只学 IA）

**不可用**
- 无抓取、无指标计算实现
- 对接的是他们商业后端

---

### 6. `huanghfzhufeng/GEO-Insight` — 仿真评分，不是真抓取

| 项 | 内容 |
|----|------|
| License | **无** |
| 实质 | Bocha 搜索 + Jina 抽正文 + **DeepSeek API 模拟各「宇宙」回答** + Judge 打分 |

**重要澄清**：不是真的登录豆包/Kimi/文心拿回答，而是「用不同检索规则 + 人设」仿真。

**可复用**
- Judge JSON schema：`is_mentioned / rank_position / sentiment_score / risk_level`
- LangGraph 式节点：dispatch → simulate → judge → aggregate
- 前端 Dashboard 组件布局

**不可当**
- 真实 GEO 投流监测数据源

---

### 7. `AI2HU/gego` — 架构不错，License 危险

| 项 | 内容 |
|----|------|
| License | **GPL-3.0** |
| 数据源 | OpenAI / Anthropic / Google / Perplexity / Ollama **官方 API** |
| 栈 | Go + Vue3 + PG + Mongo + etcd worker |

**可参考**
- 品牌 + 别名、引用 URL/域名统计
- Cron + 队列 worker 分离
- 仪表盘模块划分

**风险**
- GPL-3 衍生作品需开源；闭源 SaaS 需法务评估，**不建议作为底座 fork**

---

### 8. `sharozdawa/ai-visibility` — 演示/公式

- MIT，Next.js + Prisma + MCP
- 评分权重：**Mention 40% + Position 30% + Sentiment 30%**
- 代码中可见 **随机/模板模拟** 生成结果，非真实平台抓取
- 用途：Landing/演示、分数权重讨论、MCP 形态参考

---

### 9. 纯抓取 / 供应商 SDK

| 项目 | 说明 | 建议 |
|------|------|------|
| oxylabs/*-scraper | 付费 Scraper API 示例 | 海外 Provider 可选实现 |
| cloro-dev/*-scraper | ChatGPT/Perplexity 结构化抓取 | 研究 citations 字段结构 |
| scrapeless llm-chat-scraper-skill | Agent Skill 形态 | 后期 Agent 集成参考 |

**国内主流 Web UI 抓取几乎没有可直接生产的稳定开源方案** → 必须自建维护。

---

## 对照我们头脑风暴文档的能力缺口

| 我们需要的能力 | 开源能提供的 | 必须自建 |
|----------------|--------------|----------|
| 国内 Web 真实抓取 | geo_marketing / gitgeo 模式 | 账号池、代理、指纹、改版应急 |
| 海外模型 | elmo / aeo / gego（API 或付费 scrape） | 成本控制与配额 |
| 提及/位置/情感/SoV | aeo-platform + GEO-Insight judge + ai-visibility 权重 | 统一指标规格 + 可配置权重 |
| 多采样稳定性 | aeo-platform sampling | 任务调度集成 |
| 多租户 SaaS 看板 | elmo / deepseek-geo IA | Org/Workspace/Brand 数据模型 |
| 证据链截图 | 各项目零散 | 对象存储 + 截图流水线 |
| 告警/报告/API | 碎片化 | 产品层自建 |

---

## 推荐「拆零件」策略（不要 fork 合体）

```
我们的系统（自建 monorepo）
├── apps/web          ← 参考 elmo 结构 + deepseek-geo 页面 IA
├── apps/api          ← 参考 gitgeo FastAPI 分层
├── apps/crawler      ← 自建；模式学 geo_marketing + gitgeo probe
│   ├── providers/deepseek|doubao|kimi|yuanbao
│   └── browser (Playwright / CloakBrowser 可选)
├── packages/metrics  ← 移植 aeo-platform 算法 + 自研 SoV
├── packages/schema   ← 自建（头脑风暴实体）
└── worker/queue      ← 参考 elmo pg-boss / 或 Celery+Redis
```

### 建议落地顺序
1. **指标库 POC**（aeo 公式 Python 化 + 单测）— 1–2 天  
2. **DeepSeek Web 抓取 POC**（对照 geo_marketing 拦截模式）— 2–4 天  
3. **gitgeo 式 Probe 配置**扩展豆包/Kimi — 并行  
4. **API + DB 骨架**（Brand/Prompt/RawResponse/MetricSnapshot）  
5. **仪表盘 MVP**（提及率趋势 + 原文钻取）

### License 红线
- **无 License**：geo_marketing、GEO-Insight → 只读学习，不粘贴核心文件  
- **GPL-3**：gego → 不进主仓依赖  
- **MIT**：gitgeo、elmo、aeo-platform、ai-visibility、deepseek-geo 前端 → 可合法借鉴/改造（保留 NOTICE）

---

## 最终推荐清单（精简）

| 动作 | 项目 |
|------|------|
| 立刻精读 + 跑 demo | `gitgeo`、`elmo` |
| 抓取 POC 对照 | `geo_marketing`（只对照，不 copy） |
| 指标代码移植 | `aeo-platform` 的 mention/sampling/visibility-index |
| 评分 Prompt 参考 | `GEO-Insight` judge 节点 |
| 页面导航参考 | `deepseek-geo` views |
| 持续关注 | `awesome-geo-cn` |
| 暂缓 | gego（GPL）、ai-visibility（模拟数据）、oxylabs（付费且偏海外） |
