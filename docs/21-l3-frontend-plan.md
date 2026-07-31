# L3 前端主线方案（待你过目后正式启动）

> 日期：2026-07-31  
> 状态：**方案待确认 · 未开工**  
> 前置：L0 / L1 / L2 已验收；最小数据治理已完成（docs/19、docs/20）  
> 原则：后端 counts only；前端 rates；一步一步，不擅自扩范围  
> **页面版式需求（g1geo 对标）：** [23-l3-ui-pages](./23-l3-ui-pages.md) — 实施以 21 步骤 + 23 版式为准  
> **主对标：** [极义 GEO g1geo.com](https://g1geo.com/) 的监测/平台/报告信息架构（风格自定，不做商用全链路）

---

## 1. L3 是什么 / 不是什么

| L3 是 | L3 不是 |
|-------|---------|
| 前端用 **L2 counts 整数** 派生比率、SoV、简易综合分、趋势 | 再算一套与 L1 无关的黑盒分 |
| 看板 KPI + 下钻到原文/截图 | 浏览器里跑 Playwright / 抓 DeepSeek |
| 配置页调用已有 CRUD API | 直连 Postgres |
| TypeScript **纯函数** 模块（可单测） | 浏览器调 LLM 做情感 |

**核心公式（MVP）：**

```text
提及率      = m_mentioned / n_valid          （n_valid=0 则显示 —）
位置·头部占比 = m_head / m_mentioned         （m_mentioned=0 则 —）
SoV(本品)   = m_brand / (m_brand + Σ m_comp) （分母为 0 则 —）
综合分(示意) = w_m * 提及率 + w_p * 位置分 + w_s * 情感分
              权重来自 GET /v1/config/metrics；情感 MVP 暂无计数 → 权重重分配或显示 N/A
```

**禁止：** 把日提及率再平均成「周平均日提及率」当权威；综合分默认 **不落库**。

---

## 2. 与现状后端的契约（已具备）

| 能力 | 接口 | L3 用法 |
|------|------|---------|
| 计数 | `GET /v1/counts?brand_id&platform&prompt_id&from&to&group_by&include_fake&source` | 唯一指标数据源 |
| 口径 | `GET /v1/config/metrics` | 枚举、默认权重、分母定义 |
| 明细 | `GET /v1/responses`、详情 | 下钻全文 / mentions |
| 任务 | `POST/GET /v1/crawl-jobs` | 触发监测、看状态 |
| 配置 | brands / prompts CRUD | 设置页 |
| 证据 | `/qa/media/screenshots/{file}` 或后续正式 media 路由 | 截图预览 |
| 质检 | 现有 `/qa` | **可继续保留**，正式前端不替代 B7 运维入口 |

**数据现状（治理后，心里有数）：**

- 有效样本约 `n_valid≈11`，本品/竞品提及多为 **0**  
- 看板会先看到「低/零可见性」——**正确**，不是前端算错  
- 假数据已删；`include_fake` 默认 false  

---

## 3. 技术选型（默认建议 · 启动前可改）

| 项 | 建议 | 备注 |
|----|------|------|
| 位置 | `apps/web`（现为空目录） | monorepo |
| 框架 | **Vite + React + TypeScript** | 比 Next 更轻，VPS 静态/或 node 服务皆可；若你更熟 Next 可改为 Next |
| 路由 | React Router | 少页 MVP |
| 样式 | Tailwind CSS | 快 |
| 图表 | Recharts | 折线/柱够用 |
| 请求 | fetch + TanStack Query（可选第一期只用 fetch） | |
| 部署 | 构建静态资源由 **geo-api 挂载** 或 nginx 反代 `/` → web、`/v1` → api | 与现 VPS `:8200` 对齐方案在 F0 定 |

**对标与借鉴：**  
- **主对标版式/IA：** [g1geo](https://g1geo.com/)（监测台、平台维度、报告式总览）→ 详见 [23](./23-l3-ui-pages.md)  
- **辅：** GEO-Insight 分区、elmo 可审计下钻、deepseek-geo 菜单壳  
- 只借鉴结构，不拷贝商用代码/视觉皮肤；风格自定  

---

## 4. 页面范围：L3 MVP vs 后置

### 4.1 L3 MVP（本主线要做完才算 L3 第一期）

| 路由 | 页面 | 必备能力 |
|------|------|----------|
| `/` | 总览 | KPI：n_valid、本品提及率、SoV、有效样本数；可选按 day 的趋势（`group_by=day`） |
| `/responses` | 回答列表 | 过滤 platform/status；点进详情 |
| `/responses/:id` | 回答详情 | 全文、mentions、截图、L1 字段 |
| `/jobs` | 任务 | 列表 + 创建抓取（prompt_id + platform + samples） |
| 顶栏 | 导航 | 链到上述页；可外链 `/qa` 运维质检 |

### 4.2 L3 后置（本主线不做，列在 roadmap）

- 完整品牌/Prompt 设置台（可用 API + 临时 curl/QA 顶一阵）  
- 竞品雷达/多维对比大屏  
- 登录鉴权、多工作区  
- 情感占比图（等 L1 有 sentiment 计数）  
- 第二平台切换器（等有第二 Provider）  

---

## 5. 前端模块结构（计划）

```text
apps/web/
  src/
    api/           # 封装 /v1/counts, responses, jobs...
    l3/            # 纯函数：rates.ts, sov.ts, composite.ts + fixtures
    pages/         # Overview, Responses, ResponseDetail, Jobs
    components/    # KpiCard, TrendChart, MentionTable...
    App.tsx
  docs 交叉引用 → docs/21
```

**L3 纯函数约束：**

- 入参类型只有 counts 结构（整数）+ 权重配置  
- 出参为 number | null（null = 不可算）  
- 单测 / golden：`m=0,n=10 → 0`；`n=0 → null`；SoV 分母 0 → null  

---

## 6. 实施步骤（正式启动后的小步，每步可验收）

| 步骤 | 名称 | 产出 | 验收 |
|------|------|------|------|
| **F0** | 工程脚手架 | Vite React TS + Tailwind；开发代理到 VPS/本地 API | `pnpm dev` 能打开空白壳 |
| **F1** | API 客户端 + L3 纯函数 | `api/counts`、`l3/rates` + 单测 | 单测绿；手动对现网 counts 算出提及率 |
| **F2** | 总览页 | KPI +（有 series 时）趋势 | 数字与 `curl /v1/counts` 一致 |
| **F3** | 回答列表/详情 | 全文 + 截图 + mentions | 点 #18 类样本可下钻 |
| **F4** | 任务页 | 创建 deepseek job、列表状态 | 能触发抓取并在列表看到 success |
| **F5** | VPS 部署 | compose 增加 web 或 api 静态挂载 | 公网可打开看板（路径待 F0 定） |

**建议节奏：** 一步一确认；默认不并行开第二平台。

---

## 7. 部署草图（F5 再钉死）

**方案 A（推荐 MVP）：**  
`apps/web` build → 拷进 `geo-api` 的 `/static` 或独立 `geo-web` nginx，公网仍 `http://VPS:8200/` 或 `:8201`。

**方案 B：**  
独立 `geo-web:8300`，API 继续 `:8200`，前端 env 配 `VITE_API_BASE`。

CORS：若跨端口，API 需允许 web origin（F5 处理）。

---

## 8. 明确不做（L3 主线红线）

1. 不在前端做 LLM 情感  
2. 不在前端写 Playwright  
3. 不把比率写回 `metric_snapshots` 当权威  
4. 不借 L3 名义上第二平台 Provider  
5. 不重做 B7 QA（可链过去）  

---

## 9. 成功标准（L3 第一期）

- [ ] 浏览器打开正式前端（非仅 `/qa`）  
- [ ] 总览展示：有效样本数、本品提及率、竞品 SoV 相关数字  
- [ ] 数字可由同一时间窗的 `/v1/counts` 手工复算  
- [ ] 可从列表下钻到全文 + 截图  
- [ ] 可从 UI 触发一次 DeepSeek 抓取任务  
- [ ] `docs/21` 与代码目录 `apps/web` 一致  

---

## 10. 待你拍板后再开工的点

| # | 问题 | 默认建议 |
|---|------|----------|
| T1 | 框架：Vite React vs Next.js | **Vite React** |
| T2 | 访问端口：并进 8200 vs 独立 8300 | **先独立 8300 或静态挂 8200**（F0 定一种） |
| T3 | 设置页是否进 MVP | **否**（F 后置） |
| T4 | 是否默认 `source=deepseek_web` | **可选开关，默认全部非 fake** |

你回复「按默认启动 L3」或指出修改后，再从 **F0** 正式开工。

---

## 相关文档

- [23-l3-ui-pages](./23-l3-ui-pages.md) — **页面级需求（g1geo 排版对照）**  
- [10-data-responsibility](./10-data-responsibility.md) · [11-metrics-fe-be-split](./11-metrics-fe-be-split.md)  
- [15-b6-counts-api](./15-b6-counts-api.md) · [19-l2-acceptance](./19-l2-acceptance.md) · [20-data-governance-min](./20-data-governance-min.md)  
- [04-architecture §5](./04-architecture.md) · [22-roadmap-next](./22-roadmap-next.md)  
