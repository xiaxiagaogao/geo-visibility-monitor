# L3 前端工程框架（F0b 设计定稿）

> 日期：2026-08-04
> 状态：**设计已定 · 待实施**
> 上游：[27-l3-handoff](./27-l3-handoff.md)（冷启动交接）· [23-l3-ui-pages](./23-l3-ui-pages.md)（页面需求）· [21-l3-frontend-plan](./21-l3-frontend-plan.md)（主线方案）
> 设计稿：Claude Design 项目 `56a8ae49` 的 **v2 四屏全稿**（2a 总览 / 2b 矩阵 / 2c 证据模态 / 2d 任务）

这份文档定「**大体框架**」：目录、路由、数据流、鉴权、组件边界、纯函数契约。
**不定视觉** —— token 之外的排版、间距、质感留给后续在 Claude Design 里做。

---

## 1. 本轮新增的四条拍板

docs/27 §4 的 7 条决定继续有效，本轮补 4 条：

| # | 决定 | 理由 |
|---|------|------|
| 8 | 证据详情 = **模态 + `?rid=123` 查询参数永久链接** | 静态导出做不出 `/responses/123`，见 §2.1 |
| 9 | 写操作的 key **登录时存 sessionStorage** | 关标签页即失效，不落 localStorage / 磁盘 |
| 10 | 图表**全部手写 SVG/CSS，不引图表库** | v2 只有三种图元，全是矩形和文本 |
| 11 | 本轮交付 = **骨架 + 真数据，样式极简** | 进 Claude Design 时对着真数字调样式，不对着占位符 |
| 12 | **顺序改为「框架 + 风格先行，API 对接后置」** | 用户拍板；固定数据用真实数字顶上，见 §11 |
| 13 | 样式用 **CSS Modules + tokens.css，不引 Tailwind** | v2 稿与 Claude Design 产出都是原生 CSS，逐段搬运零翻译成本 |

---

## 2. 四个硬约束（从代码核出来的）

### 2.1 `output: 'export'` 干掉了动态路由段

静态导出要求动态段用 `generateStaticParams` 预先枚举，而 response id 持续增长。
docs/23 §3.3 设想的独立页 `/responses/:id` **按现有部署方式做不出来**。

**改为：** 证据详情是 `/responses/` 页内的模态，打开时把 `rid` 写进 URL。

```text
/responses/            矩阵 / 列表
/responses/?rid=29     同一页 + 证据模态自动展开（可分享、可刷新、后退即关闭）
```

### 2.2 开发期必须同源代理，否则 Cookie 根本不会带上

Cookie `geo_qa_key` 是 `HttpOnly + SameSite=lax`，前端直连 `96.9.213.230:8200` 属跨源，
且 API 未开 CORS。三件事会同时死：登录、`GET /v1/*`、`<img src>` 拉截图。

**解法：** `output` 只在生产构建时开，dev 保留 rewrites：

```ts
// next.config.ts
const isProd = process.env.NODE_ENV === 'production'
export default {
  output: isProd ? 'export' : undefined,
  trailingSlash: true,          // 导出成目录 + index.html，见 §2.3
  async rewrites() {
    if (isProd) return []
    const target = process.env.API_ORIGIN ?? 'http://96.9.213.230:8200'
    return ['/v1/:path*', '/qa/:path*', '/health/:path*'].map((source) => ({
      source,
      destination: `${target}${source}`,
    }))
  },
}
```

浏览器眼里全部是 `localhost:3000` 同源。`API_ORIGIN` 可改成 SSH 隧道地址。

> Next 16 对 `output: 'export'` 与 `rewrites` 并存会告警。上面这样按环境切开就不会 ——
> 生产构建时 `rewrites()` 返回空数组，生产环境本来就是同源。

### 2.3 静态产物要用目录形式，FastAPI 才认

`trailingSlash: true` 让导出产物是 `out/responses/index.html`。
Starlette `StaticFiles(html=True)` 遇到目录会找 `index.html`，缺尾斜杠时自动 302 补上。
若用默认的 `out/responses.html`，`GET /responses` 会 404 —— Starlette 不会自动补 `.html`。

### 2.4 【新发现·阻塞】全文内联高亮缺后端字段

v2 的 2c 要「在命中位置内联高亮品牌名」，docs/27 §8 说这个能力「已解锁但还没用」。
核对代码后**比交接文档写的更紧一层**：

- `match_brand` 确实返回 `offset` 与 `matched_term`（[mention.py:7](../packages/metrics/geo_metrics/mention.py:7)）
- 但 `annotate.py` 只拿它们**切了 `evidence_snippet` 就丢掉**（[annotate.py:154](../apps/api/app/services/annotate.py:154)）
- `mentions` 表**没有 offset / matched_term 列**（[entities.py:138](../apps/api/app/models/entities.py:138)）

所以不是「API 不返回」，是**库里根本没存**。要高亮就得：加两列 → 改 annotate 落库 →
`MentionOut` 暴露 → 对 35 条样本重跑 `POST /v1/responses/annotate/run`。

**这是后端活，不进本轮前端范围。** 本轮 2c 的处理：

- 证据模态照常出 **L1 命中表 + L0 全文 + 截图**
- 高亮**留接口不留假实现**：`<HighlightedText text offsets={[]} />`，`offsets` 为空即平铺渲染
- **绝不**在前端按 `matched_term` 自己重找 —— docs/27 §8 明令禁止，重造匹配逻辑会和 L1 口径分叉

---

## 3. 工程骨架

```text
apps/web/
  package.json            # pnpm · Next 16 · React 19 · TS
  next.config.ts          # §2.2
  tsconfig.json  vitest.config.ts
  app/
    layout.tsx            # Shell：Topbar + Sidebar + QueryProvider
    page.tsx              # /            总览        ← 2a
    responses/page.tsx    # /responses/  回答明细     ← 2b（+ ?rid= 开 2c 模态）
    jobs/page.tsx         # /jobs/       抓取任务     ← 2d
    login/page.tsx        # /login/      登录
  components/
    shell/      Topbar BrandPill PlatformPills RangePill Sidebar
    ui/         Panel Badge Meter DataTable Modal Skeleton EmptyState ErrorBox
    charts/     MeterCard EmphasisBars HitMatrix        # 全部手写 SVG/CSS
    evidence/   EvidenceModal MentionTable HighlightedText ScreenshotBox
  lib/
    api/        client.ts brands.ts prompts.ts counts.ts responses.ts jobs.ts config.ts
    l3/         rates.ts sov.ts matrix.ts               # 纯函数 + vitest
    filters.ts                                          # URL searchParams ⇄ Filters
    auth.ts                                             # 登录 / key 存取 / 401 处理
  styles/tokens.css       # docs/27 §5.1 的色彩 token
```

**分层规矩：**`components/` 不许直接 `fetch`，只吃 props；`lib/api/` 不许算比率；
`lib/l3/` 不许碰 `fetch` 和 React。三层各自可单独读懂、单独测。

---

## 4. 数据流

**URL query 是唯一状态源。** 刷新、分享、后退全部自洽，不引状态管理库。

```text
URL ?brand=34&platform=deepseek&from=&to=&rid=
        │
        ▼  lib/filters.ts 解析成 Filters
   TanStack Query（queryKey 就是 Filters）
        │
        ▼  lib/api/*  →  原始 counts 整数
   lib/l3/*  纯函数派生比率
        │
        ▼  components/  只吃算好的数
```

### 4.1 每页要打哪些接口

| 页面 | 请求 | 说明 |
|------|------|------|
| 全局 Shell | `GET /v1/brands`、`GET /v1/config/metrics` | 品牌切换器；口径文案不硬编码 |
| 总览 2a | `GET /v1/counts?brand_id=&group_by=none` | 四个 meter |
| 总览 2a | `GET /v1/counts?brand_id=&group_by=prompt` + `GET /v1/prompts?brand_id=` | 逐提问命中条 |
| 明细 2b | 同上两条 | 矩阵完全由 `group_by=prompt` 派生 |
| 证据 2c | `GET /v1/responses?prompt_id=&answer_status=ok`、`GET /v1/responses/{rid}` | |
| 任务 2d | `GET /v1/crawl-jobs?limit=200` + `group_by=prompt` 的 counts | 按日分组在前端做 |
| 写 | `POST /v1/crawl-jobs` | **必须带 `X-API-Key` 头** |
| 截图 | `<img src="/v1/media/screenshots/{basename}">` | 只传 basename，靠 Cookie |

### 4.2 三个必须写进代码注释的坑

1. **`group_by=prompt` 的 bucket `key` 是 prompt_id 字符串，不是提问文案**
   （[counts.py:170](../apps/api/app/services/counts.py:170)）。矩阵行标题靠 `/v1/prompts` 关联。
2. **`competitors` 数组一律按 `brand_id` 关联，不许按下标**。列顺序由
   `BrandOut.competitor_ids` 定，不由 counts 返回顺序定。
3. **`GET /v1/responses` 每行都带 `full_text`**。35 条量级无所谓，但别在矩阵渲染时
   一次拉全量 —— 只在点开格子时按 `prompt_id` 拉。

---

## 5. 鉴权流程

```text
读（GET）    Cookie geo_qa_key    fetch 同源默认带，代码里什么都不用做
写（POST）   X-API-Key 请求头     key 取自 sessionStorage
```

**登录页** `/login/`：

1. `POST /qa/login`（`application/x-www-form-urlencoded`，字段 `key`）→ 后端下发 Cookie
2. 探针 `GET /v1/config/metrics`：200 = 成功，401 = key 错
   （不去解析 `/qa/login` 的 302 Location —— 探针才是「我到底认没认证」的真答案）
3. 成功后把同一个 key 写进 `sessionStorage`，供写操作用，然后跳 `/`

**401 统一处理：** `lib/api/client.ts` 收到 401 就 `router.replace('/login/?next=' + 当前路径)`。

**红线：** Cookie 只对 GET/HEAD/OPTIONS 有效，这条由
`test_cookie_never_works_for_write_methods` 逐方法守着。前端不许为了省事把写操作改成 GET。

---

## 6. L3 纯函数契约

出参一律 `number | null`，**`null` = 不可算**，由 UI 决定显示 `—`。

```ts
rate(m: number, n: number): number | null              // n<=0 → null
sov(mBrand: number, mCompetitors: number[]): number | null   // 分母 0 → null
headShare(mHead: number, mMentioned: number): number | null
matrixLevel(r: number | null): 'zero' | 'l1' | 'l2' | 'l3'   // 0/≤33%/34-66%/≥67%
```

**单测 golden（vitest）：**

| 用例 | 期望 | 守的是什么 |
|------|------|-----------|
| `rate(0, 10)` | `0` | 零提及是真结论，不能变 `null` |
| `rate(5, 0)` | `null` | 无分母不许显示 0% |
| `rate(21, 35)` | `0.6` | 对上安踏真实数据 |
| `sov(21, [22,21,20,20,17,11,5])` | `≈0.1533` | 对上 21/137 |
| `headShare(15, 21)` | `≈0.7143` | |
| `matrixLevel(0)` | `'zero'` | 0% 是空心格不是最暗档 |

**产品级规范（docs/27 §5.3）落到组件层：** `<Meter>` 与矩阵格子的 props **强制要求
`m` 和 `n`**，没有只收 `rate` 的重载 —— 让「孤零零的百分比」在类型层面写不出来。

---

## 7. 本轮范围

**做：**

- 工程脚手架、四条路由、Shell（Topbar + Sidebar）
- 数据层（api client / TanStack Query / filters）+ 401 跳登录
- L3 纯函数 + 单测
- 四屏的**结构与真实数据**：四个 meter、逐提问条、竞品 emphasis 条、80 格矩阵、
  证据模态（L1 表 + 全文 + 截图）、任务按日分组
- `tokens.css`（docs/27 §5.1 原样落地）

**不做（本轮）：**

- 精细排版 / 间距 / 动效 —— 留给 Claude Design
- 全文内联高亮（等 §2.4 的后端字段）
- 趋势图 —— **v2 稿里就没有**：只有一天数据，画出来是假的。docs/23 的趋势模块顺延
- 品牌/Prompt 设置页、多平台对比、PDF 导出（docs/27 §12 已列）

---

## 8. 验收

| # | 验收项 | 怎么验 |
|---|--------|--------|
| 1 | `pnpm dev` 起得来，未登录访问 `/` 跳 `/login/` | 浏览器 |
| 2 | 登录后 `/` 显示 **35 / 60.0% / 21 / 35 / 71.4% / 15.3%** | 与 `curl /v1/counts?brand_id=34` 逐个对 |
| 3 | 矩阵 10×8 = 80 格与 `group_by=prompt` 逐格对上 | 抽查 3 格 |
| 4 | 「2026年跑步鞋哪个好」「健身房训练」两行本品是**红框空心 0/5、0/3** | 双峰结论要看得见 |
| 5 | 点格子 → 模态展开且 URL 出现 `?rid=`；刷新后模态仍在 | |
| 6 | 截图能显示（说明 Cookie 通到 `/v1/media/`） | |
| 7 | 切到品牌 1（土巴兔）→ 提及率 **0.0% · 0/13**，不显示 `—`、不美化 | 零状态 |
| 8 | `pnpm test` 全绿 | L3 纯函数 |
| 9 | 后端自检不受影响 | docs/27 §1 两条命令 |

---

## 9. 后续（不在本轮，但已排明）

| 项 | 内容 |
|----|------|
| 后端补 offset | `mentions` 加 `offset` + `matched_term` 两列 → annotate 落库 → `MentionOut` 暴露 → 重跑标注。解锁 2c 高亮（§2.4） |
| 部署挂载 | `deploy/Dockerfile.api` 改多阶段（node build → 拷 `out/`），`main.py` **末尾**挂 `StaticFiles(html=True)` 到 `/`，并改掉现有 `GET /` 跳 `/qa` 的行为；`/qa` 保留 |
| 风格化 | 进 Claude Design 对着真数据调版式 |

---

## 10. 修订记录

| 日期 | 说明 |
|------|------|
| 2026-08-04 | 初版：F0b 框架定稿；新增 4 条决定；发现 §2.4 高亮阻塞 |
