# GEO 监测台 · 前端

> **状态：已部署在 https://geo.example.com（线上跑的是 v1）。A1–A8 主线已闭合。**
> 2026-08-24：视觉世界换成**「暗色情报终端」**（由 `docs/STYLE-BRIEF.md` 钉死），
> 全站 13 个路由已统一到这套语言，`legacy-aliases.css` / `components/ui/` /
> `components/charts/` 已删除。**v2 全部在分支上，生产仍是 v1，等做完一次性替换。**
> 设计系统见仓库根 `DESIGN.md`；进度与欠账见 §10。
> 接口契约看 [`docs/API.md`](../../docs/API.md)（唯一权威，本文不重复字段）。
> 后端职责看 [`docs/BACKEND.md`](../../docs/BACKEND.md)。

前后端是**两个产品**，各自成熟设计。这份文档只写前端：信息架构、页面、组件约定、以及几条不能破的纪律。

---

## 1. 现在树里有什么

```text
src/
  styles/tokens.css      设计 token —— 暗色情报终端。**改色前先读文件头那四条**
  styles/fonts.css       自托管 Geist + Geist Mono + 思源黑体 600 子集

  components/canvas/     **签名物件** AnswerCanvas —— 登录页/证据页/报告封面复用同一个
  components/kit/        原语：TickScale（数据记号）· Plate · Instrument/Readout* ·
                         Mark · Notation · Table · Blank/Fault/Pending ·
                         RecordStrip · TraceBars · HitGrid
  components/runs/       RunSwitcher · RunNowButton · GapList · SampleTable（只吃 props）
  components/shell/      Sidebar Topbar ThemeToggle
  components/evidence/   HighlightedText（按 first_offset 切片，不自己搜正文）

  lib/l3/                rates gaps matrix samples evidence brands prompts users
                         home run-status platforms search-used csv gap-export
                         **trend citations** + 共 238 个测试（不碰 fetch/React）
  lib/api/               client.ts（唯一取数出口）· auth · brands · prompts · users ·
                         tasks · counts · responses · crawl-jobs · **citations**
  lib/auth-context.tsx   AuthProvider / useAuth / useRequireAuth
  lib/types.ts           照 API 契约定的类型

  app/(dashboard)/       /tasks · /tasks/new · /tasks/[id] · …/runs/[runId] · …/r/[rid]
                         **/citations** · /brands · /brands/new · /brands/[id] · /users
  app/login/             已打通
```

`components/ui/` 与 `components/charts/` **已删除** —— 全站只剩一套 token、一套原语。

**取数一律走 `lib/api/`**，没有第二个出口；派生一律走 `lib/l3/`，组件只吃 props。
**刻意还没有的：** 状态管理库 —— 每个页面自己 `useEffect` 取数就够，
没有跨页共享的服务端状态，引一个 store 只会多一层要同步的东西。

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
/brands/new                              新建品牌（workspace_id 建完不可改）
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
┌ 任务头   任务名 · 品牌记号 · 平台 · 采样数 · 共几次运行
│          run 切换器 [2026-08-23 · 21 个采样 ▾]   [编辑] [立即运行]
├ 纸带     ★ 全部运行沿真实时间轴排开。本品一道线、竞品一条区间带，
│          平台集变过处**断开不连线**并标出每段的平台集。点任意一次即可切 run
├ 仪器面板  **一块面**四个读数（不是四张卡），中间用刻线分隔：
│          有效样本 │ 提及率 │ 首位提及率 │ 覆盖缺口
│          每个比率读数下面是**按分母切格的刻度尺**
├ 面板     逐提问 —— 让总提及率当场自我解释；每道的格数就是那条提问采了几次
├ 面板     覆盖缺口清单（完整）
└ Tab      命中矩阵 │ 样本列表
```

**为什么纸带排在读数前面：** 一个孤零零的「66.7%」说不清自己处在什么位置。
得先知道它在这条记录上的位置、以及中间有没有换过口径。
这 12 次的平台集换过 4 次 —— 不标断口就是把口径变化伪装成表现变化。

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

三层各自可单独读懂、单独测。`lib/l3` 的那 200 多个测试就是这条边界的产物 ——
它们不需要浏览器、不需要 mock fetch，因为那一层压根碰不到这两样。

---

## 4. 降级态 ≠ 空态

**「没采到数据」和「这个维度后端还没算」必须用不同文案**，否则用户会以为采集坏了。

| 位 | 状态 | 文案方向 |
|----|------|---------|
| 情感 | 后端 `sentiment` 恒 NULL，等接 LLM | 「暂无情感数据」 |
| 推荐率 | `is_recommended` 恒 False，counts 无 `m_recommended` | **整个指标不做**，不是降级 |
| ~~引用分析~~ | ~~citations 全库 0 行~~ | **已推翻，整页已做**：P2-37 打通千问 SSE 之后有 144 条引用 / 40 个域名，落在 `/citations` |

前两条仍然成立，措辞要注意：它们不是「还没接」，是「当前无法提供」。
写成「尚未接入」会让人以为在排队上线。

第三条**已经过期并被删除** —— 留着一条已经不成立的「不做」比没有更糟：
它会让下一个接手的人绕开一个其实已经可用的能力。

---

## 5. 明确不做

| 项 | 理由 |
|----|------|
| ~~跨 run 趋势图~~ | **已推翻，已做**。「只有一个采集日」那条理由在 2026-08-23 不再成立：任务 27 有 12 次运行（08-08 ~ 08-23）。做成了任务详情页顶部那条**纸带**，重点不是画线是**标断口** —— 这 12 次的平台集换过 4 次，连成平滑一条就是把口径变化伪装成表现变化。判据与限度见 `lib/l3/trend.ts` |
| Share of Voice | 需要显著度加权 + 时序，两样都缺 |
| 平台引用分布环形图 | 仍然不做，但**理由换了**：不再是「只有 DeepSeek」（现在跑的是千问），而是**当前任务仍是单平台**。单平台构成比是一根 100% 的条，画出来是假装有多样性 |
| 检测报告（叙述性） | LLM 生成的报告现在做就是编数据 |
| 图表库 | 图元只有刻度尺、纸带、矩阵三种，全是矩形、线和文本，手写 SVG/CSS 即可。改版后仍然成立 |
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

开发期取数走 `next.config.ts` 里的 rewrites 代理到 `geo.example.com`。
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

已于 2026-08-11 上线：`deploy/Dockerfile.web` + compose 的 `web` 服务，
容器 `geo-web` 端口只绑 `127.0.0.1:3000`（公网只能经 Caddy 进）。
post-receive 会一并 build 并起它，尾部有直连 3000 的探针。

**前端与 API 同源**，都在 `https://geo.example.com`，Caddy 按路径分流：

```caddyfile
http://geo.example.com, https://geo.example.com {
	handle /v1/*    { reverse_proxy 127.0.0.1:8200 }
	handle /qa/*    { reverse_proxy 127.0.0.1:8200 }
	handle /health* { reverse_proxy 127.0.0.1:8200 }
	handle          { reverse_proxy 127.0.0.1:3000 }   # geo-web 容器
	tls internal
}
```

**必须同时收 `http://` 与 `https://`**：Cloudflare 是 Flexible 模式、回源走 HTTP:80，
只写 https 的话 Caddy 会自动 308 到 HTTPS、CF 原样返回 → 无限重定向。

对应 env：`CORS_ALLOW_ORIGINS` 留空 · `API_COOKIE_SAMESITE=lax` ·
`API_COOKIE_SECURE=true` · `CSRF_PROTECTION_ENABLED=true`。

改 Caddy 的顺序是**先起进程、确认 `127.0.0.1:3000` 活着，再改 handle** ——
反过来会有一段 `/` 是 502 的中间态。

---

## 10. 交接（冷启动看这里）

### 现在到哪儿了（2026-08-23）

**页面主线全部完成。视觉改版已完成 4/11 个路由。**

| 阶段 | 状态 |
|---|---|
| A1 `lib/api` + 登录 · C1 CSRF · B1/B2 上线 | ✅ |
| A5 任务列表 + 新建任务 | ✅ 含第一个真实写操作 |
| A6 任务详情 `/tasks/[id]` | ✅ 含「样本列表」tab |
| A7 证据页 `/tasks/[id]/runs/[runId]/r/[rid]` | ✅ 高亮走 L1 `first_offset`，带不变量自检 |
| A8 客户首页分流 | ✅ 判定在 `lib/l3/home` |
| **A2/A3/A4 品牌 / 提问词 / 用户管理** | ✅ **已完成**（提问词做在 `brands/[id]/PromptsPanel`，不是独立路由） |
| **P2-37 联网标注 + 引用来源** | ✅ 证据页渲染引用；样本表加「联网」列 + 四档筛选 |
| **视觉改版 v1**（熏烟纸地震图） | ⚠️ **已作废**。上过生产一天，2026-08-24 被风格 brief 替换 |
| **视觉改版 v2**（暗色情报终端） | ✅ 全站 13 个路由已统一；旧原语与过渡层已删 |

---

### 视觉改版：现在是什么

**视觉世界由 `docs/STYLE-BRIEF.md` 钉死**（用户提供的风格情报），
不是我发明的、也不是 impeccable 骰子分配的 —— **brief 优先于 roll**。

> 暗色情报终端。一种强调色。回答流是唯一装饰。登录和监测台共用同一个签名物件。

方向契约写在 `src/app/layout.tsx` 顶部，以 HTML 注释形式活到生产构建之后
（一份构建擦掉的契约没人能审）。**设计系统的完整记录见仓库根 `DESIGN.md`**；
产品事实见 `PRODUCT.md`。

**签名物件是 Answer Canvas**（`components/canvas/`）：一段模型回答，本品高亮、
竞品次级、引用行内小票。登录页播它、证据页还是它、将来报告封面还是它 ——
复用三次以上才叫识别度。

**刻度尺**（`components/kit/TickScale.tsx`）仍在，但它是**数据记号**不是签名物件，
和 Answer Canvas 不在同一层。它承担「分母可见」：轨道宽度固定、按分母切成 n 格 ——
提及率 18 格、首位提及率 12 格，一眼看出这两个百分比的分母不一样。

**三处一定要读代码注释再动的地方：**

1. `src/styles/tokens.css` 文件头 —— 四条硬约束。最要紧的两条：
   **文字层级的下沿没有余量**（白 48% 正好 4.98:1，再淡就不合格）；
   **顺序色阶只用于不承载文字的填充**（三档色阶的中段是死区，
   白字 3.92、深字 3.93，两边都够不到 4.5）。改色阶要重跑 `dataviz` 验证器。
2. `scripts/fonts/README.md` —— 中文是**子集**，只含仓库里出现过的汉字。
   **改了界面文案要重跑 `bash scripts/fonts/build-cjk-subset.sh`**，
   否则漏掉的字会单独掉回系统字，一个词里两种字形。
3. `components/canvas/AnswerCanvas.tsx` —— 高亮只来自 L1 的 `first_offset`，
   组件内部再验一次不变量，对不上就不画。**这条自检不是摆设**：
   做登录页时手数的演示偏移全错，高亮落在了「价位」「跑者」上。

**L3 层的两个新模块**（口径逻辑仍然全部在纯函数里，组件只吃 props）：
`lib/l3/trend.ts`（跨 run 序列 + 断点判据，19 条测试）、
`lib/l3/citations.ts`（榜单派生，12 条测试）。测试共 **238** 条。

### 还欠的账

1. **⚠️ 招聘方打不开这个站。** 所有页面都要登录 —— 简历链接发出去，看的人没有账号。
   2026-08-23 明确**不做**演示模式/演示账号（「按正常项目做，不要因为演示就乱改」），
   所以这条靠截图与录屏解决。**它仍然没有被解决。**
2. **仍然没有组件级 / 端到端测试。** 238 条全是纯函数。而 v2 那次全站扫荡
   一次改了 24 个文件，完全没有网兜着。`webapp-testing` 就是干这个的。
3. **登录后的页面在 v2 下没有经过人眼确认。** 那一轮 Chrome 扩展断连、
   浏览器面板又没有会话。代码层面全绿（lint / 238 / build / 检测器结构类 0 命中），
   视觉未验。
4. **纸带 `kit/RecordStrip` 还是 v1 的形态。** 按 `STYLE-BRIEF.md` §8.2
   它应该是**单色面积图**；文件里还留着「纸带 / 触针 / 刻线」这类 v1 注释。
5. **生产上跑的仍是 v1。** v2 全部在分支上，等做完一次性替换。
6. **已知分歧（未压掉）**：impeccable 检测器把 **Geist 判为 `overused-font`**，
   而 `STYLE-BRIEF.md` §7.2 点名它是第一选择。brief 优先，用户 2026-08-24 确认保留。

### 本机怎么跑

```bash
cd apps/web && pnpm test && pnpm lint && pnpm build
```

dev server 在 `.claude/launch.json` 里叫 `web`、端口 3100（`preview_start {name: "web"}`），
`/v1` 由 `next.config.ts` 的 rewrites 代理到线上。**后端仍然只在 VPS 上跑。**

### 改版时别优化掉的东西

这个项目真正稀有的不是视觉，是它在很多地方**拒绝说好听的话**。
懂行的人看到这些会比看到渐变和动效印象深：

- **「未标注」≠「未提及」** —— 前者是我们还没跑 L1，后者是 AI 真没提
- **联网标注三态** —— `null`（不知道）单独一档，不许并进「未联网」
- **高亮只来自 L1 标注**，对不上就画红色告警，**不做 `indexOf` 兜底**
- **比率永远跟着 `m/n`**，孤零零的百分比不给
- **非 `ok` 的样本照列但标「不进分母」** —— 不标的话用户会拿表行数去对 KPI

**「样本列表」tab 的降级态已经拆掉。** A6 上线时它是降级态，原因是
`/v1/responses` 与 `/v1/crawl-jobs` 都没有 `run_id` 过滤（列那一列是有的，
只是没暴露成查询参数）。后端已补：两个端点都加了 `run_id`，
另加一个 `GET /v1/responses/summary` 轻量投影 ——
列表一行都不显示 `full_text`，却要为它拖几百 KB 过网，
所以那个端点**不带 `full_text` 也不带 `raw_json`**（API.md §7）。

样本表里两条要守住的口径：

- **非 `ok` 的样本照列，但标「不进分母」**。不标的话用户会拿表里的行数
  去对 KPI 里的「有效样本」，然后以为哪边算错了。
- **「未标注」不等于「未提及」**。前者是我们还没跑 L1，后者是 AI 真没提。
  显示成同一个词就是把降级态说成结论。

失败的 job **不产出 `RawResponse`**，所以它在样本表里一行都不占 ——
「这次运行还有几条没回来」只能另打一次 `/v1/crawl-jobs?run_id=&status=failed`
取 `total`。不数这一次的话，一个 partial 的 run 看起来和完整跑完的一模一样。

行里的**样本 id 链到证据页**。链 id 那一列而不是整行：整行可点的话，
选中一段预览文字松开鼠标就会跳走 —— 而那段预览正是用来扫读的。

### 证据页那条不变量（A7 的全部重点）

```
full_text.slice(first_offset, first_offset + matched_term.length) === matched_term
```

高亮位置**只来自 L1 标注**，渲染前再验一次这条不变量（`lib/l3/evidence.ts`，14 个测试）。
对不上的那一处**不画**，改成页面上一条红色告警，写明标注说什么、原文实际是什么。

**不做 `indexOf` 兜底。** 拿 `matched_term` 自己去正文里找，等于在前端重造一套
匹配逻辑（大小写折叠、别名优先级都在后端），口径当场分叉；更糟的是找到的那处
很可能不是 L1 数的那处，而页面看起来完全正常 —— 用户会拿一段错的原文去跟客户
解释结论。静默画错比空着糟得多。

`runId` 在证据页**只用来生成返回链接，不参与任何数字**：样本由 `rid` 唯一确定，
而 `/v1/responses/{id}` 并不回传它属于哪个 run。所以 URL 里的 run 就算对不上，
也不会出现「按错的 run 报数」——最多是竞品名取不到、显示成 `#id` 的可见降级。

顺带记一笔矩阵：格里**只显示 `m/n`，不显示 `#N`**。设计稿那一档要的是
「该品牌在这几次采样里的中位出场顺位」，那是个分布，而 counts 只给得出
`m_first` 这一个计数 —— 拿它反推名次是编数据。设计稿允许省掉 `#`，
所以这不是缺陷，是「绝不伪造名次」的落地。

### 视觉来源

**由 `docs/STYLE-BRIEF.md` 钉死**（用户提供的风格情报），不是从零发明、
也不是 impeccable 骰子分配的结果 —— **brief 优先于 roll**。

历史（都已作废，别再照它们加新页面）：
- ~~两个 Claude Design 项目（GeoMonitor / L3 设计系统 v2）~~ —— 2026-08-23 替换
- ~~v1「熏烟纸地震图」，impeccable seed `e13eab31`~~ —— 2026-08-24 替换，
  它在生产上跑过一天

完整设计记录见仓库根 `DESIGN.md`。


### 开发闭环

~~本机不起服务。~~ **这条已经不成立**：前端在本机跑得起来，
改版第一批全程是在 `localhost:3100` 上截图验收的。

```bash
cd apps/web && pnpm test && pnpm lint && pnpm build
```

dev server 在 `.claude/launch.json` 里叫 `web`、端口 3100，
`/v1` 由 `next.config.ts` 的 rewrites 代理到线上 —— 浏览器眼里全是同源，
**和生产行为一致**（生产是 Caddy 按路径分流，也是同源）。
登录态会落到 localhost 名下，所以本机能看到真实数据。

推 main 之后 post-receive 仍会自动 build `geo-web`，
在 https://geo.example.com 上看线上效果。
后端需要真库的测试在 VPS 容器里跑，详见 `docs/BACKEND.md` §10。

### 现网可联调的真实数据

⚠️ 下面这组是 **2026-08-23 重新实测的**。上一版这里写的是 run 27 的
`n_valid 35 · m_mentioned 21`，那是 2026-08-06 的快照，早就不是最新一次运行了。

```text
task 27「安踏监测集」· brand 34 安踏 + 7 个竞品 · 共 12 次运行（08-08 ~ 08-23）

最新一次 run 300（partial）：
  counts?brand_id=34&run_id=300  →  n_valid 18 · m_mentioned 12 · m_first 1
  21 个采样只回来 18 条 —— 分母少一截，比率偏高

全时段累计（跨 run，只有引用榜与联网分桶该用它）：
  n_total_responses 191 · n_valid 180（11 条 too_short）
  m_mentioned 112 · head 71 / middle 30 / tail 7 · m_first 25 · citation_only 4

引用：144 条 / 40 个域名
  www.163.com      12 次 / 12 条样本   ← 覆盖面广
  www.toutiao.com   9 次 /  4 条样本   ← 集中引用，榜单上挨着但不是一回事
联网分桶：**只有两桶** true=19 · unknown=161，**false 桶不存在**
  （界面不能假设三桶都在，但要把三档都画出来）

另有 brand 1 土巴兔：本品 0 提及、6 个竞品有命中 —— 零状态的真实用例
```

> 重抓后会变。对数前先跑一次 `/v1/counts` 确认，别照抄这里的数字。

### 最容易踩的三个坑

1. **别绕过 `apiFetch` 直接 `fetch`** —— 那是唯一会漏掉 CSRF 头的方式，
   而开关已经开了，漏了就是 403。
2. **counts 必须带 `run_id`** —— 不带算的是跨 run 混算 + **当前**竞品集，
   两次打开会因为别人改了配置而变。
3. **改 Caddy 前先确认 `127.0.0.1:3000` 活着**，反过来有一段 502 中间态；
   且站点必须同时收 `http://` 与 `https://`（CF 是 Flexible 模式，回源走 80）。
