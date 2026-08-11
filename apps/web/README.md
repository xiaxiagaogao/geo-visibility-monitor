# GEO 监测台 · 前端

> **状态：IA 已定稿，页面待重建。** 树里现在只有组件库、设计 token、L3 纯函数和外壳骨架。
> 接口契约看 [`docs/API.md`](../../docs/API.md)（唯一权威，本文不重复字段）。
> 后端职责看 [`docs/BACKEND.md`](../../docs/BACKEND.md)。

前后端是**两个产品**，各自成熟设计。这份文档只写前端：信息架构、页面、组件约定、以及几条不能破的纪律。

---

## 1. 现在树里有什么

```text
src/
  styles/tokens.css      设计 token（浅色为主 + 深色可切，色阶跑过对比度验证器）
  components/ui/         Panel Badge Kpi* Table Tabs EmptyState Degraded ErrorState Skeleton
  components/charts/     EmphasisBars（手写 SVG/CSS，不引图表库）
  components/shell/      Sidebar Topbar ThemeToggle
  components/evidence/   HighlightedText
  lib/l3/                rates.ts · gaps.ts + 29 个测试（纯函数，不碰 fetch/React）
  lib/types.ts           照 API 契约定的类型
  app/(dashboard)/       只有一个占位页
  app/login/             版式就绪，接口未接
```

**没有的：** `lib/api/`、状态管理、任何真实取数。

之前有一套围绕**单个**品牌构建的五页看板，已整体移除——根因不是页面质量，是前提错了：
`OWN_BRAND_ID` 是模块级常量，派生数据的七个 selector 全是零参数函数，而后端从第一天起
就是多品牌的（`GET /v1/brands` 返回列表，`/v1/counts` 的 `brand_id` 必填）。
要看那五个页面：`git show cdb4a97:apps/web/src/app/'(dashboard)'/page.tsx`

---

## 2. 信息架构

### 2.1 底层模型（后端已上线，见 §6）

```text
Workspace
  └ Brand ── aliases · competitor_ids · Prompt[]
                    ▲
                    │ brand_id（一对一）
Task「命名的监测定义」── 平台 · 采样数 · 提问集选择
  └ Run「一次执行」
       ├ 快照：prompts[] · competitor_ids[] · platforms[]
       └ CrawlJob × N ──► RawResponse ──► Mention
```

**Run 的三份快照是这个模型的全部价值所在。** 没有它，任务列表只是个好看的分组；
有了它，两次 run 之间的差异才是**表现变化**而不是**口径变化**。

具体防的是什么：提及率的分母是提问集，缺口清单与失分量取决于竞品集。
两者都可改（`PUT /v1/brands/{id}/competitors` 是整体替换语义）。
不快照的话，八月给某品牌加一个竞品，七月那次 run 的缺口清单会当场重算、历史结论被改写。

### 2.2 路由

```text
/login                                   邮箱 + 密码

── 超管 / 运营 ──────────────────────────────────
/tasks                                   任务列表 ← 首页
/tasks/new                               新建任务
/tasks/[id]                              任务详情（自动落到最新 run）
/tasks/[id]/runs/[runId]                 指定某次运行
/tasks/[id]/runs/[runId]/r/[rid]         单条回答证据
/brands                                  品牌列表
/brands/[id]                             品牌详情：别名 / 竞品 / 提问词
/users                                   用户管理（仅超管）

── 客户 ────────────────────────────────────────
/                                        重定向到自己品牌最新 run
可达 /tasks/[id]/...，列表接口服务端自动收敛到本 workspace
```

**首页按角色分流。** 运营管多个客户品牌，任务列表就是他的工作台；
客户通常只有一个任务，让他先看一个单行列表再点进去是多余的一层。

**证据是真路由，不是查询参数。** 运营要把证据链接发给客户，
`/tasks/34/runs/128/r/29` 和 `?id=34&run=128&rid=29` 在一个商业产品里不是同一回事。

### 2.3 任务详情页

```text
┌ 任务头  任务名 · 品牌徽章 · 平台 chip
│         run 切换器 [2026-08-02 ✓ 35条 ▾]        [立即运行]
├ KPI ×4  有效样本 │ 提及率 │ 首位提及率 │ 覆盖缺口
├ 面板    逐提问 emphasis 条 —— 让 KPI 里那个总提及率当场自我解释
├ 面板    覆盖缺口清单（完整）
└ Tab     命中矩阵 │ 样本列表
```

**为什么缺口不进 tab：** 它是这个产品里最接近「告诉我该干什么」的东西，
输出可以直接交给推流团队。藏进第三个 tab 等于把唯一可执行的产出降级成附录。

**为什么逐提问分布必须紧跟 KPI：** 总提及率是各条提问平均出来的，
可能由「几条满分 + 几条挂零」构成。大数字单独站着会掩盖这个结构，
而这个结构才是结论。

---

## 3. 三条不能破的纪律

### 3.1 凡显示比率，必须同时显示 `m / n`

孤零零的百分比在这个产品里没有可信度。这条在**类型层面**守着：
`<KpiRate>` 只接受 `m` 和 `n`，没有接收算好的 `rate` 的重载。

### 3.2 `null` 是「不可算」，`0` 是「真的是 0」

`rate(m, n)` 在 `n <= 0` 时返回 `null`，UI 显示 `—`。
`rate(0, 10)` 返回 `0`，UI 显示 `0.0%` —— 零提及是真实结论，不许美化成 `—`。

### 3.3 时间窗一律 `Σm / Σn`，绝不把日比率求平均

分母不等时两者不相等，平均出来的数字没有任何口径。
这是「后端只给整数」这个分层的根本理由（API.md §4.2）。

### 3.4 分层边界

```text
components/   不许直接 fetch，只吃 props
lib/api/      不许算比率
lib/l3/       不许碰 fetch 和 React
```

三层各自可单独读懂、单独测。`lib/l3` 的 29 个测试就是这条边界的产物。

---

## 4. 降级态 ≠ 空态

**「没采到数据」和「这个维度后端还没算」必须用不同文案**，否则用户会以为采集坏了。

| 位 | 状态 | 文案方向 |
|----|------|---------|
| 情感 | 后端 `sentiment` 恒 NULL，等接 LLM | 「暂无情感数据」 |
| 推荐率 | `is_recommended` 恒 False，counts 无 `m_recommended` | **整个指标不做**，不是降级 |
| 引用分析 | citations 全库 0 行，根因是采集时从未开联网搜索 | **整页不做**。要有数据需开联网 + 重抓，而重抓会破坏与现有基线的可比性 |

第三条尤其要注意措辞：它不是「还没接」，是「当前无法提供」。
写成「尚未接入」会让人以为在排队上线。

---

## 5. 明确不做

| 项 | 理由 |
|----|------|
| 跨 run 趋势图 | Run 成为一等实体后结构上支持了，但目前只有一个采集日，画出来是假的。等跑出三次以上再加 |
| Share of Voice | 需要显著度加权 + 时序，两样都缺 |
| 平台引用分布环形图 | 只有 DeepSeek，单平台构成比是一根 100% 的条，画出来是假装有多样性 |
| 检测报告（叙述性） | LLM 生成的报告现在做就是编数据 |
| 图表库 | 只有 emphasis 条与矩阵两种图元，全是矩形和文本，手写 SVG/CSS 即可 |
| Tailwind / UI 框架 | 设计稿产出是原生 CSS，CSS Modules 逐段搬运零翻译成本 |

---

## 6. 前端 IA 依赖的后端能力（已全部上线）

前端 IA 建立在 `Task` / `Run` 之上。定 IA 时这两个实体后端还不存在，
当时列了五项依赖：

1. `tasks` 表：`brand_id`、命名、平台、采样数
2. `runs` 表：`task_id`、平台快照。**没有 status 列** —— 由其下 job 的状态派生，
   存一份就要有人同步，而一个和实际漂移了的状态列比没有更糟：它看起来权威
3. 两张快照表：`run_prompts`（含 `prompt_text`，因为提问词正文可改）、
   `run_competitors`（含 `brand_name`，且刻意不设到 `brands` 的外键——
   竞品被删后「当时拿它比过」这个事实仍应留着）
4. `crawl_jobs` 加 `run_id` 外键（**可空**：迁移前已有的 job 没有 run）
5. `GET /v1/runs/latest` —— 客户首页分流要用；顺带 `/v1/counts` 支持 `run_id` 过滤，
   否则任务详情的 KPI 算的是该品牌历史全部样本，不是这一次

**以上五项已于 2026-08-08 全部上线并验证。** 现网可直接联调：

```text
GET /v1/tasks              → 1 条「安踏监测集」（task 27），latest_run_status=success
GET /v1/runs/latest        → run 27，快照 10 条提问 + 7 个竞品
GET /v1/counts?brand_id=34&run_id=27   → 35 / 21，与不带 run_id 时一致
```

那 35 条历史样本已回填到 run 27。它的 `note` 里写明「快照按回填时的配置补，
与后续运行不完全可比」—— 因为当时的提问集与竞品集没有记录，这是补出来的。

所以前端现在不再有后端阻塞，下一步是 `lib/api` 基础设施 + 登录打通。

---

## 7. 鉴权与写操作

身份只有一条通道：**会话 Cookie**。`X-API-Key` 是机器凭证，权限等同超管，
**绝不打进前端包**（API.md §1）。

**CSRF token 从响应体拿。** `login` 与 `me` 的响应体都带 `csrf_token`，
存**内存**（别进 localStorage）。同源之后 `document.cookie` 也读得到 `geo_csrf`，
但仍走响应体 —— 不依赖 Cookie 作用域，将来变拓扑不用改前端。

```ts
// 所有写操作无条件带 CSRF 头，不给「先不带以后再加」留口子
fetch(url, {
  method: 'POST',
  credentials: 'include',                        // 同源下是默认行为，写明让意图清楚
  headers: { 'X-CSRF-Token': csrfToken, 'Content-Type': 'application/json' },
})
```

`credentials: 'include'` 同源下是默认行为，写明只是让意图清楚。

后端 `CSRF_PROTECTION_ENABLED` **已于 2026-08-11 打开**：
没带这个头的会话写操作一律 403。`lib/api/client.ts` 对
POST/PUT/PATCH/DELETE 无条件带上，所以走这一层就不会漏。

**别绕过 `apiFetch` 直接调 `fetch`** —— 那是唯一会漏掉这个头的方式。

**401 与 403 必须分流处理：**

- `401` 未登录 / 会话过期 → 跳登录页
- `403` 已登录但没权限，或 CSRF 校验失败 → **不要跳登录页**，会陷入登录循环。提示「无权限」
- `404` 不存在**或不属于你** —— 二者对外不可区分（防枚举），当作「没有这条」处理

前端按 `role` 隐藏按钮只是体验，**不是安全边界**。权限判断始终在服务端。

---

## 8. 开发

```bash
pnpm install
pnpm dev      # 默认 3000；仓库的 .claude/launch.json 用 3100
pnpm test     # vitest
pnpm lint     # tsc --noEmit
pnpm build
```

开发期取数走 `next.config.ts` 里的 rewrites 代理到 `geo.xg22.top`。
本机 `localhost:3000` 和线上不是同一个 Origin，代理让浏览器眼里全是同源，
**和生产行为一致**（生产是 Caddy 按路径分流，也是同源）。

---

## 9. 部署

**Node 运行时**（`output: 'standalone'`），不是静态导出。
`pnpm build` 产出 `.next/standalone/server.js`，起这个进程即可。

换来两样：**真实路由**（`/tasks/[id]` 不必用 `generateStaticParams` 预枚举 id），
以及**服务端能在渲染前拦未登录**（同源之后 Cookie 与前端同域，Next 服务器看得见）。

> 后一条曾经不成立并被撤回过 —— 那是前后端分成两个域名的时候。
> 2026-08-11 合并成同源之后它重新成立了。

代价是 VPS 上多一个常驻进程。Caddyfile 已经配好（见下），不必再动。

> **还差最后一步：** `deploy/` 下还没有前端的 Dockerfile / compose 服务，
> 所以 `/` 目前是 503 占位。Caddy 站点已经建好了（下面就是现行配置），
> 部署 Next 进程时不用再动它。

**前端与 API 同源**，都在 `https://geo.xg22.top`，Caddy 按路径分流：

```caddyfile
http://geo.xg22.top, https://geo.xg22.top {
	handle /v1/*    { reverse_proxy 127.0.0.1:8200 }
	handle /qa/*    { reverse_proxy 127.0.0.1:8200 }
	handle /health* { reverse_proxy 127.0.0.1:8200 }
	handle          { reverse_proxy 127.0.0.1:3000 }   # ← B1/B2 部署 Next 后填这里
	tls internal
}
```

**必须同时收 `http://` 与 `https://`**：Cloudflare 是 Flexible 模式、回源走 HTTP:80，
只写 https 的话 Caddy 会自动 308 到 HTTPS、CF 原样返回 → 无限重定向。

对应 env：`CORS_ALLOW_ORIGINS` 留空 · `API_COOKIE_SAMESITE=lax` · `API_COOKIE_SECURE=true`。
当前 `/` 是 503 占位，等 Next 进程部署上去（B1/B2）。
