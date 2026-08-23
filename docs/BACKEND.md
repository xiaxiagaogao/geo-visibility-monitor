# GEO Demo · 后端核心说明

> **后端唯一现行文档**（由历史 01–27 全部提炼而成，归档已删除）。  
> **冲突时以本文 + 代码为准**；本文与代码冲突时以代码为准，并回来改本文。  
> 前端另成产品、另写文档。**给前端看的接口契约在 [API.md](./API.md)** —— 本文只写后端职责与内部约定。

---

## 1. 定位

| 项 | 约定 |
|----|------|
| 项目 | GEO **可见性监测**。学习项目，但**按商业级系统设计** —— 不拿「这是 demo」当简化理由 |
| 后端产品 | 配置监测对象 → 抓取 AI 回答 → L1 标注 → **L2 计数 API** + 明细/证据查询 |
| 前端产品 | 给**运营**用的检测工具（不是单品牌看板）；展示与比率/图表**不在本文展开** |
| 运行方式 | **本机只写代码**；**VPS 跑** API / crawler / Postgres |
| 首发平台 | DeepSeek Web；豆包 / Kimi / 通义后置 |

**后端不做：** 返回提及率/SoV 当权威、浏览器调 LLM、账号池规模化、内容生成与发布、
告警中心 / 周报 PDF / Webhook。

**用户体系与三角色权限（超级管理员 / 运营 / 客户）已实现** —— 见 §5。
共享密钥 `API_KEY` 保留为**机器凭证**（脚本 / 运维 / CI），不下放给前端。

**`/qa`：** 运维质检页，不是正式产品前端。

---

## 2. 指标分层（拍板，勿再改口径）

```text
L0 原文/引用/截图     → 后端存储
L1 单次判定           → 后端规则标注（可版本化重跑）
L2 整数计数           → 后端 GET /v1/counts（实时聚合；日表物化后置）
L3 比率/综合分/趋势   → 前端用 counts 相除（默认不落库）
```

| 规则 | 说明 |
|------|------|
| 分母 | 仅 `answer_status = ok` → `n_valid` |
| 分子 | `mentions` 上 `m_mentioned` / 类型 / 位置桶等 **整数** |
| **presence hit** | `m_mentioned` 计入 **body 与 citation_only 两种**；`m_body` / `m_citation_only` 是它的拆分，不是并列口径 |
| 假数据 | counts 默认 `include_fake=false` |
| `metric_snapshots` | 表可存在（历史占位含 rate 列），**永不当 L2 真相源** |
| 综合分权重 | 可经 `/v1/config/metrics` 下发，**计算在前端** |
| 情感 | 若做：后端 L1 后置；**禁止前端调 LLM** |

**公式（前端侧，便于联调）：**  
`提及率 = m_mentioned / n_valid`；`SoV = m_本品 / (m_本品 + Σ m_竞品)`；`n_valid=0` 或 SoV 分母为 0 时显示不可用。

### 2.1 比率不可加（最容易犯的错）

**任意时间窗的比率 = Σm / Σn，绝不是「日比率的算术平均」。**

分母不等时两者不相等；把日比率存下来再平均，得到的数字没有任何口径。
这条是「后端只给 counts」这个分层的**根本理由** —— 只要前端拿到的是整数，
就不可能在时间窗上算错。

推论：`/v1/counts` 永不返回比率字段；`metric_snapshots` 永不作为权威。

### 2.2 双端一致性

L1 判定在后端 Python（`packages/metrics`），L3 派生在前端 TypeScript。
同一公式两处实现必然漂移，靠三件事约束：

1. **golden fixtures 双边对照** —— 同一组输入，两边算出同一组输出
2. 口径（枚举、默认权重）由 `/v1/config/metrics` 下发，前端不硬编码
3. 版本戳：`annotator_version` 变了就要重跑，否则新旧标注混在一个分母里

**L3 纯函数的入参只接受 counts 整数，不接受比率类型** —— 从类型上堵死「拿比率再算比率」。

---

## 3. 域模型（要点）

字段以 `apps/api/app/models/entities.py` 为准；本节只记**带决策含义**的部分。

```text
Brand ──< Alias
Brand ──< CompetitorLink >── Brand
Brand ──< Prompt ──< CrawlJob ──< RawResponse
Brand ──< Task ──< Run ──< CrawlJob（run_id 可空：Task/Run 之前的旧 job 没有）
Run ──< RunPrompt · RunCompetitor（口径快照）
RawResponse ──< Mention（每回答×每品牌唯一，DB 有 UNIQUE 约束）
RawResponse ──< Citation
```

| 表 | 层 | 要点 |
|----|----|------|
| brands | 配置 | 有 **`workspace_id`（默认 1）**，`GET /v1/brands` 可按它过滤 —— 目前**唯一的隔离键**，做「客户」角色时是地基。它是最初 `Org → Workspace → Brand` 三层归属模型的残留，上面两层从未建表 |
| brand_aliases / competitor_links | 配置 | 别名勿过宽（见 §6）；竞品**也是 brand 行**，不是字符串 |
| prompts | 配置 | 监测提问；**正文不应含监测品牌名**（见 §6） |
| crawl_jobs | 采集 | pending → running → success/failed；**`sample_index` = 同一 prompt 的第几次采样**。一条 job = **一个样本**，不是一个批次。`environment_id` 见 §7.4 |
| crawl_environments | 采集 | **一行 = 一种采集环境**（P2-36），不是一行一次抓取。见 §7.4 |
| crawl_credentials | 采集 | 登录态健康度快照（P2-07），每平台一行。见 §7.3 |
| raw_responses | L0+L1 | `full_text` 必须是**原文**；`answer_status`；`annotator_version` |
| mentions | L1 | 见下方字段说明 |
| citations | L0 | **当前全库 0 行**，根因见 §7.0 |
| tasks | 配置 | 命名的监测定义：一个主品牌 + 平台 + 采样数，可反复执行 |
| runs | 采集 | 一次执行。**刻意没有 `status` 列** —— 由其下 job 的状态派生（`services/tasks.py:derive_run_status`）。存一份就要有人同步，而 job 状态在 worker 里变、run 在 API 里变，漂移是迟早的事，而漂移了的状态列比没有更糟：它看起来权威 |
| run_prompts / run_competitors | 采集 | **口径快照**，见下方 §3.4 |

**「一次检测」现在有实体了**（`tasks` / `runs`），此前只能按 `created_at` 日期分组硬凑。
一条 job 仍然 = 一个样本；`run_id` 把一批 job 归成一次执行。

**answer_status：** `ok` \| `empty` \| `too_short` \| `error`  
（侧栏误抓、明确假数据等 → `error`，不进分母。）

**mention_type：** `body` \| `citation_only` \| `none`

**position_bucket：** 按**首次**提及的 offset 把全文三等分  
`head = offset < L/3` · `middle = < 2L/3` · `tail = 其余` · 未提及 = `null`  
（当前 annotator：`l1-rules-v3`）

### 3.1 出场顺位 position_rank（口径必须说清）

**含义是位置事实，不是推荐名次。** 命名与展示都不要说成「首推」。

- 正文命中的品牌按 `first_offset` 升序 1-based 排名
- 只有 `mention_type=body` 有名次。`citation_only` 是 `NULL` —— 正文根本没出现，
  没有「出场位置」可言，**不是排在最后**
- **只在被监测品牌集合内排序**。若回答先提到未监测的品牌，我方 `rank=1` 仍是 1，
  含义是「我们关心的品牌里它最先出现」，不是「全文第一个品牌」
- 同 offset（别名重叠）按 `brand_id` 兜底，保证同输入同输出

实现见 `services/annotate.assign_position_ranks`。

### 3.2 first_offset / matched_term 与一条不变量

```text
full_text[first_offset : first_offset + len(matched_term)] == matched_term
```

**前端靠这条自检高亮有没有错位**（`first_offset` 非空时成立）。

`matched_term` 落库的是**原文片段**，不是 `match_brand()` 返回的折叠形式 ——
正文写 `Nike` 而 `match_brand` 给的是 `nike`，直接落库会让展示大小写不符、
且上面那条不变量不成立。见 `services/annotate.surface_term`。

`citation_only` 命中时 `first_offset` 为 `NULL`（正文没出现），此时不变量不适用。

> 前端**禁止**自己拿 `matched_term` 去正文里重找 —— 会和 L1 口径分叉。

### 3.3 仍然恒空的两类字段

| 列 | 当前值 | 缺什么 |
|----|--------|--------|
| `sentiment` / `sentiment_score` | 恒 `NULL` | 计划由后端接 LLM（L1 后置） |
| `is_recommended` | 恒 `False` | 「推荐/首选/建议选择」启发式未接入流水线 |

`packages/metrics` 里 `score_sentiment()` / `is_recommended()` 的实现是有的，
但只挂在 `/v1/analyze/*` 那两个无状态玩具接口上，**L1 标注流水线没调**。

连带后果：`/v1/counts` 没有 `m_recommended`，**前端算不出推荐率**；
情感相关的一切展示都没有数据源。要用就得先扩 L1 白名单并重跑标注。

---

### 3.4 口径快照：这个模型唯一「冗余」的部分，也是它唯一的价值

发起一次 run 时，**先把当次口径冻结进快照表，再按快照建 job**。顺序不能反：
反过来的话，两步之间任何一次配置修改都会让 job 用新口径跑、快照记旧口径，
而这**不会报错**，只会让某次 run 的数字对不上它自己的快照。

| 快照 | 存了什么 | 为什么 |
|------|---------|--------|
| `run_prompts` | `prompt_id` **+ `prompt_text`** | 提问词正文可改。只存 id 的话，历史运行的问题会跟着变 |
| `run_competitors` | `competitor_brand_id` **+ `brand_name`**，**刻意不设到 `brands` 的外键** | 竞品品牌被删之后，「当时拿它比过」这个事实仍应留在历史运行里 |
| `runs.platforms` | 平台 code 列表（JSONB） | 平台不是实体，只是注册表里的 code，建关联表没有收益 |

**防的是什么：** 提及率的分母是提问集，缺口清单与失分量取决于竞品集，两者都能被随时改
（`PUT /v1/brands/{id}/competitors` 是整体替换语义）。不冻结的话，
八月给某品牌加一个竞品，七月那次 run 的结论会被当场重算。

**这条纪律要贯穿两层，少一层都会静默出错。**

| 层 | 函数 | 带 run_id 时读 |
|----|------|---------------|
| 统计 | `services/counts.py:competitor_ids` | `run_competitors` 快照 |
| **抽取** | `services/annotate.py:target_brand_ids` | `run_competitors` 快照 |

只做统计层是不够的 —— 那样分母对上了、竞品集还是活的，快照只用了一半。

**只做统计层还有一个更隐蔽的洞：** 统计层能查对的前提是「该查的 mention 行本来就存在」。
run 冻结竞品集 `[A, B]` 之后，若在 job 跑完前有人整体替换了竞品配置，
或对失败 job 做了 `retry`，抽取层会按**当时的活配置**生成 mention 行 ——
于是 `counts` 按快照要 `[A, B]`，而 B 的行压根没生成。
B 就从「有算」变成「未算」，**不报错、不可见**。

不带 `run_id` 是品牌级累计口径（跨 run），此时没有「当时」可言，只能用当前配置；
`run_id` 为空的 ad-hoc job（走 `/v1/crawl-jobs` 直接建的）行为不变。

**`/v1/counts` 传 `run_id` 时还会校验两件事**：这个 run 你看得见
（`assert_run_visible`），以及它确实属于这个 `brand_id`（否则 404）。
不校验的话，拿自己的 brand_id 配别家的 run_id 能把对方快照里的竞品 id 枚举出来。

---

## 4. API 地图

Base：`http://<host>:8200`。字段以代码 `apps/api/app/api/*` 为准。

| 域 | 方法 | 路径 |
|----|------|------|
| 根 | GET | `/` → **302 到 `/qa`**（前端要占 `/` 需先改这里） |
| 健康 | GET | `/health`（公开）· `/health/db` · `/health/config`（需 Key，返回 crawl_mode / worker / auth 开关） |
| 品牌 | CRUD | `/v1/brands` · `/v1/brands/{id}` |
| 品牌别名 | PUT | `/v1/brands/{id}/aliases`（整体替换） |
| 竞品关系 | PUT | `/v1/brands/{id}/competitors`（整体替换 id 列表） |
| Prompt | CRUD | `/v1/prompts` · `/v1/prompts/{id}` |
| 任务 | GET/POST | `/v1/crawl-jobs` · `/{id}` · `/{id}/retry` · `/worker/run-once` |
| 检测任务 | CRUD | `/v1/tasks` · `/v1/tasks/{id}`（PATCH 不含 `brand_id`，过不了户） |
| 发起运行 | GET/POST | `/v1/tasks/{id}/runs` |
| 运行 | GET | `/v1/runs/latest`（**路由必须排在下一条之前**，否则 `latest` 会被当成 id 解析成 422）· `/v1/runs/{id}`（带口径快照） |
| 明细 | GET | `/v1/responses` · `/{id}` |
| 重标 | POST | `/v1/responses/{id}/annotate` · `/annotate/run` |
| 计数 | GET | `/v1/counts`（**`run_id` 会同时切换竞品集到快照**，见 §3.4） |
| 登录 | POST | `/v1/auth/login`（公开）· `/v1/auth/logout` · GET `/v1/auth/me` |
| 用户 | CRUD | `/v1/users` · `/v1/users/{id}` —— **仅超管** |
| 登录态健康度 | GET | `/v1/health/credentials` —— **仅超管/运营**，见 §7.3 |
| 口径 | GET | `/v1/config/metrics` |
| 平台可用性 | GET | `/v1/config/platforms` —— 前端据此渲染 chip，**勿硬编码平台清单**（见 §7.1） |
| 灌入 | POST | `/v1/ingest/l0`（非主路径） |
| 截图 | GET | `/v1/media/screenshots/{file}`（`/qa/media/...` 是同一处理函数的别名） |
| 质检 | GET/POST | `/qa` · `/qa/login` · `/qa/logout` · `/qa/responses`… |
| **勿用** | POST | `/v1/analyze/response` · `/v1/analyze/batch` —— 无状态玩具接口，不读库、不落库，与 L1/L2 口径无关 |

**两个 PUT 是整体替换语义**，不是增量。前端改竞品集合要先读全量再整体提交。

### `/v1/counts`（L2）

| 参数 | 说明 |
|------|------|
| `brand_id` | 必填（监测主品牌） |
| `platform` / `prompt_id` / `from` / `to` | 过滤；`to` **含当天末**（纯日期补到 23:59:59.999999） |
| `group_by` | `none` \| `day` \| `platform` \| `prompt` |
| `include_fake` | 默认 `false` |
| `source` | 可选，如 `deepseek_web` |

**`group_by=prompt` 的 bucket `key` 是 prompt_id 字符串，不是提问文案** ——
要行标题得自己去 `/v1/prompts` 关联。同理 `group_by=day` 的 key 是 **UTC 日期**。

**响应里 `competitors[]` 一律按 `brand_id` 关联，不许按数组下标** —— 顺序不保证。

### 列表分页

`/v1/responses` 与 `/v1/crawl-jobs` 支持 `limit`（≤200）+ `offset`；
响应里的 `total` 是**过滤后的全量计数**，不受分页影响，前端据此算页数。

**不做：** `category` 过滤参数（前端读 `/v1/prompts` 自行归类）。  
**不做：** API 直接返回提及率等比率权威字段。

---

## 5. 鉴权与权限（D2）

### 5.0 三条身份通道（并存，互不替代）

| 通道 | 载体 | 身份 | 用途 |
|------|------|------|------|
| **用户会话** | Cookie `geo_session`（HttpOnly） | `users` 行，带角色与 workspace | **前端唯一通道** |
| **共享密钥** | `X-API-Key` / `Bearer` | **等同超管**，无用户身份 | 脚本、运维、CI、`verify_l2` |
| **QA 后门** | Cookie `geo_qa_key` | **等同超管**，仅 GET/HEAD/OPTIONS | `/qa` 运维质检页 |
| **完全免鉴权** | — | — | `/health` · `/qa/login` · `/v1/auth/login` · `/favicon.ico` |

认证在**中间件**（`ApiKeyMiddleware`），解析结果放 `request.state.principal`。
放中间件是为了 **fail-closed**：默认拒绝，只有 `PUBLIC_PATHS` 例外 ——
改成逐路由挂依赖的话，漏挂一个就是一个开放接口。

**授权在路由依赖**（`require_write` / `require_superadmin` / `assert_*_visible`）：
中间件看不到路径与查询参数，做不了归属校验。

- 公网必须配置 `API_KEY`（`deploy/.env`，chmod 600）；空 key = **完全无鉴权**，启动打 WARNING
- 未认证且 `Accept: text/html` 的 GET → 302 到 `/qa/login`；否则 401 JSON
- 已登录但没权限 = **403**，不是 401 —— 401 会让前端以为该重新登录，陷入登录循环

### 5.1 角色与权限矩阵

| 能力 | 超管 | 运营 | 客户 |
|------|:---:|:---:|:---:|
| 看数据（counts / responses / 截图） | 全部 | 全部 | **仅本 workspace** |
| 品牌 / 别名 / 竞品 / 提问词 增改删 | ✓ | ✓ | ✗ |
| 发起抓取、重试、重标注、灌 L0 | ✓ | ✓ | ✗ |
| 用户增删改 | ✓ | ✗ | ✗ |

`users.workspace_id` **只对 client 有意义**（= 他能看的品牌范围，对上 `brands.workspace_id`）；
超管/运营为 NULL。客户是**纯只读**：抓取消耗 DeepSeek 登录态且不可撤销，不放给外部角色。

### 5.2 归属校验：三个口子，第三个最隐蔽

**不可见一律 404，不是 403。** 403 等于确认「该 id 存在但不属于你」，
客户据此能枚举出别家有多少品牌、多少样本。

| # | 口子 | 做法 |
|---|------|------|
| 1 | 显式带 `brand_id` / `prompt_id` 的接口 | 逐个 `assert_brand_visible` / `assert_prompt_visible` |
| 2 | 列表接口的**默认范围** | 客户身份下强制注入 workspace 过滤，不是可选参数。`/v1/crawl-jobs` 更严：客户必须带 `prompt_id`，任务列表本身就泄露别家在监测什么 |
| 3 | **截图按 basename 取，与品牌毫无关联** | 反查 `screenshot_path` → response → job → prompt → brand → workspace |

> 第 3 条是**结构性缺口**：文件名带时间戳、可枚举。前两条堵了、这条不堵，等于全白做。

**`visible_workspace_id` 必须 fail-closed。** 它用 `None` 表示「看全部」，
所以「本该受限却拿不到 workspace」的两种情况必须显式拒绝，否则就是放行全部：
匿名（401）、角色是 client 却没有 workspace_id（403，直接改库能造出这种行）。

### 5.3 CSRF

D2 之前靠「Cookie 只对 GET 有效」挡 CSRF。**会话能用于写之后这条自动作废**，
换成**双提交 token**：登录下发 `geo_csrf`（**刻意非 HttpOnly**，前端要读它回填
`X-CSRF-Token`）→ 服务端比对 Cookie 与请求头。跨站页面能让浏览器带 Cookie，
但同源策略让它读不到值，拼不出匹配的头。

- 开关 `CSRF_PROTECTION_ENABLED`，**2026-08-11 已在生产打开**（compose 默认值仍是 false）。
  打开前核过三条身份通道：①`X-API-Key` 不过 CSRF ②用户会话写操作才校验
  ③`/qa` 后门 Cookie 只对安全方法生效。开启后实测：① PATCH 200、③ 登录 302 + 读 200、
  ③ 拿 qa cookie 做写操作 401、读接口 200
- 只影响**会话身份的写操作**；`X-API-Key` 不受影响（请求头本就得调用方主动设置，本来免疫）
- `/qa` 后门 Cookie 仍**只对安全方法有效**，这条老防线保留

### 5.4 同源部署：一个域名，按路径分流

前端与 API **同源**，Caddy 在 `geo.xg22.top` 上按路径分流：

```caddyfile
http://geo.xg22.top, https://geo.xg22.top {
	handle /v1/*    { reverse_proxy 127.0.0.1:8200 }
	handle /qa/*    { reverse_proxy 127.0.0.1:8200 }
	handle /health* { reverse_proxy 127.0.0.1:8200 }
	handle          { reverse_proxy <前端进程> }
	tls internal
}
```

**必须同时收 `http://` 与 `https://`。** Cloudflare 是 Flexible 模式、回源走 HTTP:80；
只写 `https://` 的话 Caddy 会对 HTTP 请求自动 308 到 HTTPS，CF 原样返给浏览器 ——
**无限重定向，且请求根本到不了应用**。同机的 fund / option 也都是这么成双配的。

对应的 env：

```bash
CORS_ALLOW_ORIGINS=        # 留空 → CORS 中间件整个不启用
API_COOKIE_SAMESITE=lax    # 同源不需要 none
API_COOKIE_SECURE=true     # HTTPS
```

#### 为什么从两个域名合回来（D1 → 2026-08-11）

D1 曾把前端拆到独立域名，根因是「前端另成产品」被理解成了「另一个 Origin」——
**这是两件事**。跨 Origin 收的税：

- CORS 三项配置必须成套，缺一项现象是「登录了但一直 401」，无任何报错
- CORS 中间件顺序坑：现象是「浏览器全挂但 curl 正常」
- `SameSite=None` 强制 `Secure`
- **前端读不到 `geo_csrf`**（host-only Cookie），双提交 CSRF 根本实施不了
- 服务端拦不了未登录（Next 同样看不到另一个域的 Cookie）
- 证据截图 `<img src>` 只能靠跨站 Cookie

而 `geo-api.xg22.top` 实际只承接了 `/qa`（7 天 24 个请求，拆开看基本是扫描器）。
合并后上述六条一次性消失，该域名退役（DNS 记录仍在 Cloudflare，放回 block 即可恢复）。

> CORS 相关代码与测试**保留**：`CORS_ALLOW_ORIGINS` 非空时仍会启用，
> 将来真要拆分不用重写。

### 5.5 CDN 会绕过鉴权 —— 需要鉴权的响应必须禁缓存

线上拓扑：`浏览器 → Cloudflare（真证书）→ Caddy（tls internal）→ geo-api:8200`。

**Cloudflare 按文件扩展名缓存静态资源。** `/v1/media/screenshots/*.png` 是需要
鉴权的证据文件，但 URL 以 `.png` 结尾 —— 若源站不表态，CF 会把它存到边缘节点，
之后**任何拿到 URL 的人都能取到，请求根本到不了我们的中间件**。

这个洞只在套 CDN 后出现，本机与直连 `:8200` 都复现不了。2026-08-05 实测：
未登录请求返回 `200 · cf-cache-status: HIT`。

**防线：**

1. 响应带 `Cache-Control: private, no-store`（已落地，有行为测试守着）。
   加了之后 CF 对该路径变为 `cf-cache-status: BYPASS`，未登录请求正确 401。
2. **建议**在 Cloudflare 再加一条 Cache Rule：`/v1/media/*` → Bypass cache，
   作为「有人改掉响应头」时的兜底。

> **新增任何返回文件的接口时，先问一句「它会不会被 CDN 缓存」。**
> 判断依据是 URL 后缀与 `Cache-Control`，不是路径前缀。

---

## 6. 监测数据口径（从实践收束）

### 6.1 提问词

- **禁止**「安踏和李宁哪个好」这类**点名本品**的题 → 提及率必然接近 100%，测不到可见性。  
- 应用无提示品类/场景题，例如「国产运动鞋品牌有哪些值得买的？」。  
- `seed_anta.py` 里有**断言守着这条**：提问词出现监测品牌名直接报错退出。

### 6.2 别名

- 勿用裸 `361`（会匹配正文里任何 361 数字）；用 `361°` / `361度`。  
- 集团子品牌是否计入本品要单独定口径，勿与主品牌混算（例：安踏 vs 斐乐/迪桑特）。
  监测的是**消费者品牌**，不是集团口径；要看集团是另一套指标。

### 6.3 现网演示集（可并存，counts 按 `brand_id` 隔离）

| 集 | 用途 |
|----|------|
| **安踏 + 7 竞品**（主演示） | 无提示题；用来验收比率/SoV 是否「算得出」 |
| 土巴兔等旧集 | **零提及**用例：真抓样本从未命中其别名，L3 上看到 0% 是真实口径**不是 bug** |

具体 id 以库内数据为准；对接时用 API 列表查询。

**基线快照（2026-08-02，`verify_l2 --brand-id 34` PASS）** —— 改 L1 规则重跑后拿它对照：

```text
n_valid = 35（answer_status 全部 ok，零 error）
安踏 m=21 → 60.0%   head 15 / middle 5 / tail 1
竞品区间 14.3%(鸿星尔克 5) ~ 62.9%(亚瑟士 22)
SoV(安踏) = 21 / 137 = 15.3%
出场顺位分布（安踏 21 次命中）：#1×6 · #2×5 · #3×5 · #4×4 · #5×1
```

> 2026-08-05 升 `l1-rules-v3` 重跑全部 50 条样本后，上面每个数字**逐个不变** ——
> v3 是纯增量（只补 `first_offset` / `matched_term` / `position_rank`）。
> 全库 179 条正文命中，`substr(full_text, first_offset+1, len(matched_term))`
> 与 `matched_term` **179/179 完全吻合，零错位**。

**这套数据的双峰结构是刻意配比出来的，不是巧合：**

```text
国产 / 性价比 / 篮球类提问   →  安踏 5/5、4/4、3/3、3/3、3/3  （100%）
专业跑鞋 / 健身训练类提问     →  安踏 0/5、0/3                 （0%）
```

全通用向会把本品压到 0%，全国产向会推到 100%，两种极端都看不出趋势。
**60% 是这两极平均出来的** —— 只看总数会掩盖真问题，所以 `group_by=prompt` 是必需能力。

### 6.4 假数据与脏抓

- 删除或排除 `raw_json.source` 为 `fake*` / 正文以 `【假数据` 开头。  
- 侧栏误抓（如「开启新对话」开头）→ `answer_status=error`，不进分母。  
- 治理脚本：`app.scripts.data_governance_min`，**默认 dry-run**（见 §10）。

---

## 7. 抓取实现约束（DeepSeek · 易错点）

这些是代码 review / 真抓后的**硬约束**，不是流水账：

| 约束 | 原因 |
|------|------|
| L0 `full_text` **存原文** | 旧逻辑「清洗后写库」会不可逆破坏正文；清洗结果只进 `raw_json.cleaned_text` |
| **优先 DOM** 取答 | 纯流式拼接会丢首块；`_pick_answer_text` 以 DOM 为真值，stream 只在 DOM 明显更短时兜底 |
| 位置 = **首次**提及 | 按别名长度降序抢先命中会系统性偏 tail |
| offset 必须能对**原文**切片 | 归一化改长度（`strip` / `casefold`）会导致 evidence 错位；用长度守恒的 `_fold()` |
| 证据截图：抽回答 → 独立页渲染 → full_page | 直接对聊天页 full_page 会带侧栏/输入框；渲染页要带 CSP |
| 不落库 DeepSeek 会话 URL | 多会话上下文串扰；证据靠截图 |
| 抓完即删会话（走侧栏 UI） | 防历史堆积污染 DOM 抓取 |
| **删除会话的接口 HTTP 200 不代表删成功** | DeepSeek 把错误放在 body 里（如 `code:40002`）。**验收必须核对真实状态，不能信日志** |
| 清理脚本默认 dry-run | `deepseek_cleanup.py` —— 账号里绝大多数是用户私人对话，误删不可逆 |
| 登录 | `DEEPSEEK_STORAGE_STATE`；禁止提交 Git |
| 僵死 `running` | 超时（`CRAWL_STUCK_JOB_SEC`，默认 600s）回收为 failed；`retry` 放行 running；勿只捞 pending |
| DELETE 品牌/Prompt | ORM 关系须配 `cascade` + `passive_deletes=True`，否则 SQLAlchemy 会先把子表外键置 NULL 而撞 NOT NULL → 500 |

source 常见：`deepseek_web`（另有历史 `chrome_bridge` / fake，默认计数排除 fake）。

### 7.0 引用（citations）为什么一条都没有

**结论：全库 0 行 / 50 条回答。这不是解析 bug，是回答里本来就没有引用。**

2026-08-06 实测：

| 检查 | 结果 |
|------|------|
| 正文含「已阅读 N 个网页」（联网标志） | **0 / 50** |
| `raw_json` 含 `cite` 字样 | 0 |
| `raw_json` 含 `search` 字样 | 0 |
| `raw_json` 含 http 链接 | 1 —— 是 id=6 的**会话 URL**（旧 `chrome_bridge` 路径遗留），不是引用 |

两层原因，**顺序不能颠倒**：

1. **抓取时从未开启 DeepSeek 的联网搜索。** 不联网就没有引用来源可解析 ——
   这是主因，改代码也变不出数据
2. `_extract_citations` **只在非 SSE 分支里跑**（`response.json()` 那条），
   而 DeepSeek 走的是流式 —— 即使将来开了联网，这条路径也抓不到

另外 `raw_json` **不存响应体**，只存元数据（`source` / `stream_chunks` 计数 /
`session_deleted` / `captured_at`），所以也无法从存量数据里回捞引用。

**要做引用分析，需要三步（缺一不可）：**

① provider 里点开「联网搜索」开关 → ② `_extract_citations` 也在 SSE 分支调用
→ ③ 重抓样本

> ⚠️ **③ 会破坏现有基线的可比性。** §6.3 的 35 条（安踏 60.0%）是在**不联网**
> 条件下测的；联网会改变回答内容分布。混着统计就没有口径了 ——
> 要么整套重抓，要么把联网样本单独成集。这是产品决策，不是实现细节。

### 7.1 平台：「已知」与「能跑」是两件事

`app/providers/registry.py` 是**唯一真相源**，加平台只改这一个文件。

| 概念 | 含义 | 现状 |
|------|------|------|
| **已知平台** | `platform` 列的合法取值，历史数据按它解释 | `deepseek` `doubao` `kimi` `tongyi` |
| **已实现** | real 模式下真有 Provider 能跑完 | **只有 `deepseek`** |

- 未接入的平台**建任务时就返回 400**，不会放到 worker 才 failed
  —— 后者会让人误判成「抓取出错」，而真相是「这个平台没接」
- **fake 模式下所有已知平台都可跑**（走 `FakeProvider`），本机/CI 造数据靠这个
- 前端读 `GET /v1/config/platforms` 渲染 chip：`available` = 现在建任务能否跑完；
  `implemented` = 有没有 real Provider。fake 模式下 `available=true` 但 `note`
  会明写「产出的是假数据」，**不骗前端**

> **`ALLOWED_PLATFORMS` 不等于「能跑」。** 它现在从注册表派生，仅表示「已知」。

> **存量污染不可回填。** 早期样本的 L0 被旧清洗规则改写过、且丢了首块，
> 重跑 L1 也补不回来 —— 要干净数据只能重抓。安踏那 35 条是修复后抓的，是干净的。

### 7.2 失败分类与自动退避重试（2026-08-14 起）

采集出口迁到大陆家宽之后，**每次 run 开头一两条会被限流**
（`Page.goto: Timeout 120000ms exceeded`），之后就顺。

| 组件 | 位置 |
|---|---|
| 分类规则 | `app/services/failure_kinds.py`（纯函数） |
| 退避曲线与决策 | `app/services/retry_policy.py`（纯函数） |
| 落库 | `app/services/crawl_jobs.fail_job()` · `claim_pending_jobs()` |

**只有 `timeout` 与 `rate_limited` 会自动重试。** 取值表见 `API.md` §8.0.1。
`unknown` 刻意不重试 —— 自动重试一个没认出来的失败，是用 3 倍时间撞同一堵墙，
还会把原始信号淹掉（最后留在 `error_message` 里的是第 3 次的报错）。

四条需要记住的机制：

1. **退避落库，不在进程里 sleep。** sleep 会串起整批（`run_once` 是串行循环），
   而且 job 留在 `running` 会被 `CRAWL_STUCK_JOB_SEC` 的僵死回收收成 failed，
   两套机制打架。落库之后退避中的 job 回 `pending`，claim 跳过它去领下一条。
2. **claim 的条件是** `status='pending' AND (next_attempt_at IS NULL OR <= now)`。
   `NULL` = 立刻可领 —— 迁移前的旧行、**冷备那台旧代码 crawler 建的行**都是 NULL。
3. **claim 清 `error_message` / `failure_kind` / `next_attempt_at`，不清 `attempt`。**
   清了重试上限就形同虚设。
4. **限流是全局现象，per-job 退避只是缓解。** 现在观察到的是「头一两条」，
   所以 per-job 够用。**如果哪天变成大面积限流，要的是全局降速/熔断，
   不是把 `CRAWL_MAX_ATTEMPTS` 往上堆** —— 后者只会让一次 run 变得极慢。

分类不认识的失败会打 `kind=unknown` 的 WARNING 日志，
`grep kind=unknown` 就能捞出「下一个该提上来的模式」。

---

### 7.3 登录态健康度（P2-07，2026-08-15 起）

| 组件 | 位置 |
|---|---|
| 判级规则 | `app/services/credential_health.py`（纯函数） |
| 落库 | 同文件 `report_credentials()`，**由 crawler 调用**，写 `crawl_credentials`（迁移 008） |
| 出口 | `GET /v1/health/credentials`（仅超管/运营），见 `API.md` |

**为什么要经数据库中转**：`storage_state` 在采集节点上，而 api 跑在 VPS ——
api 读不到那个文件。**P2-34 之后（2026-08-20）已改成 POST 上报，表确实没动** ——
判级仍在节点算（`collect_reports`，纯函数），落库走 `POST /v1/worker/credentials`
到共用的 `store_report`。⚠️ `checked_at` 由**服务端**盖章，不接受节点上报：
它是「多久没听到节点动静」的信号，用节点的时钟，钟一歪这个信号就说假话。

四条：

1. **看的是「从哪儿签发的」，不是「多久没成功」。** WAF cookie 的名字直接暴露
   签发地（`HWWAFSES*` = 华为云 = 境内，`aws-waf-token` = AWS = 境外）。
   2026-08-15 那次故障里「上次成功抓取」一直是几分钟前 —— **它只能发现
   「全红」，发现不了「悄悄降级」**。
2. **绝不读取、绝不落库 cookie 的值。** 只存名字、域、过期时间。值是凭证本身，
   落进库或日志就等于把登录态复制到一个没人当它是凭证的地方。有用例钉着。
3. **认不出签发地就不报不匹配。** 接新平台时 `issuer_region` 一开始必然是
   `unknown`，报红会让这个端点第一天就没人看。
4. **一条都没上报 ≠ 健康** —— `overall` 返回 `unreported`。

`CRAWL_TIMEZONE_ID` · `CRAWL_EXPECTED_CREDENTIAL_REGION` · 容器跑在哪台机器上
**是同一件事的三个面**，切冷备时要一起改（`scripts/crawl-node/deploy.sh` 里
`GEO_TZ` / `GEO_EXPECT_REGION` 两个环境变量）。

---

### 7.4 采集环境指纹（P2-36，2026-08-15 起）

| 组件 | 位置 |
|---|---|
| 指纹与探测 | `app/services/crawl_env.py`（指纹是纯函数） |
| 落库 | 同文件 `upsert_environment()`，worker 每 `CRAWL_CREDENTIAL_CHECK_SEC` 刷新 |
| 打标记 | `claim_pending_jobs(..., environment_id=)` —— **领取那一刻** |
| 出口 | `GET /v1/runs/{id}` 的 `environments[]` / `n_jobs_unstamped` |

指纹的六个维度：`node_label` · `exit_ip` · `timezone_id` · `crawl_mode` ·
`credential_region` · `waf_kind`。**任何一维变了就是另一种环境。**

四条：

1. **一行 = 一种环境。** 环境很少变，job 每天几十条。
   `SELECT DISTINCT environment_id FROM crawl_jobs WHERE run_id=?`
   **多于一行就是混了** —— 这是一次查询就能得到的事实，不是回忆。
2. **指纹可读不做哈希**，缺失维度写 `-` 不省略（否则不同环境会撞成同一个指纹）。
3. **探不到就留 NULL，不编默认值。** 上线前的 run 全部 `unstamped`，那是事实。
4. **改 `FINGERPRINT_FIELDS` = 改「什么算同一种环境」**，加维度会让历史环境行
   全部变成「另一种」。加之前想清楚值不值。

**跨 run 比数字之前先比指纹** —— 指纹不同的两次运行，差异里混着环境变化。

---

### 7.5 浏览器指纹加固（2026-08-15 起）

`app/providers/browser.py` —— provider 与 `scripts/export_storage_state.py` 共用。

**为什么有它**：豆包第一条探针提问就把登录态打掉了（`?from_logout=1`）。
节点实测，旧用法有四个破绽：

| 检测点 | 旧 headless | 新 headless + 本模块 |
|---|---|---|
| `navigator.webdriver` | `True` | `False` |
| `navigator.plugins` | `0` | `5` |
| `window.chrome` | `undefined` | `object` |
| User-Agent | `HeadlessChrome/131.0.6778.33` | `Chrome/131.0.0.0` |

四条：

1. **`channel="chromium"`（新 headless）白送 `plugins` 与 `window.chrome`** ——
   这两项本来只能靠注入伪造，一行配置省掉整个 stealth 层。
2. **UA 必须显式覆盖。** 参数改不掉它，而它比 `webdriver` 还直白。
   `strip_headless_marker` 只换标记不编版本号 —— 编了会在升级镜像后过期。
3. **出生环境要等于使用环境。** 用 `launch_persistent_context` + `user_data_dir`，
   不用 `storage_state=` 移植 —— 会话在一种浏览器里出生、另一种里使用本身就是信号。
4. **不做 stealth 注入。** 只做「看起来像普通浏览器」，不做「伪装成别人」；
   笨拙的注入本身就是指纹，不一致的覆盖比不覆盖更可疑。

> **DeepSeek 刻意还没迁过来。** 它用旧路径跑了一年没出事，
> 而调试新平台时不能同时改动唯一在工作的平台。等豆包稳定后再单独决定。

**实测确认（2026-08-15）**：加固之后无头发提问**不再被登出**
（`POST /chat/completion` → 200 `text/event-stream`，会话存活）。
所以「无头」本身不是问题，指纹才是 —— **不需要上 Xvfb**。

`seed_storage_state()`：`launch_persistent_context` **不接受 `storage_state=`**
（那是 `new_context` 的参数），所以要手动灌。顺序不能反 ——
**先 cookies，再导航到该 origin，最后写 localStorage**：
localStorage 按 origin 隔离，没导航过去就没有可写的存储区。

---

## 8. 前后端契约（后端保证）

1. 展示用指标：**只信** `/v1/counts` 整数，前端自己除；时间窗一律 Σm/Σn（§2.1）。  
2. 下钻：`/v1/responses` + `/v1/media/screenshots/...`。  
3. 写操作必须 Key 头；读可在同源 Cookie 下工作（§5）。  
4. 未接入平台不要假定有数据；灰显由前端处理。  
5. 改 L1 规则会升 `annotator_version` → 需重跑 annotate 旧数据才一致。  
6. 排名、情感、推荐率**当前无数据**（§3.1）；前端应走「暂无数据」降级，**不得自行推算**。

---

## 9. 组件与目录

| 组件 | 说明 |
|------|------|
| `apps/api` | FastAPI **和** 抓取 worker（`app.worker_main`）都在这里 |
| `packages/metrics` | 匹配/分桶/情感等纯逻辑 + 单测 |
| `deploy/` | compose、Dockerfile、post-receive hook（存根 + `deploy.sh` 正文，见 §10.2）、init.sql |

容器：`geo-api` · `geo-crawler` · `geo-postgres`。
**`geo-crawler` 容器跑的是 `apps/api` 的 `app.worker_main`** —— 曾经有个
`apps/crawler/` 目录无人引用，已删除（`Dockerfile.crawler` 从来只 COPY `apps/api`）。

```text
本机 push main → VPS post-receive 存根（强制 checkout main）→ exec deploy/deploy.sh（docker compose up）→ /opt/geo-demo
```

---

## 10. 运维速查

| 项 | 值 |
|----|-----|
| VPS | `96.9.213.230`（Ubuntu 24.04） |
| 公网入口 | `https://geo.xg22.top`（Cloudflare 橙云 → Caddy 按路径分流 → `127.0.0.1:8200`）。**`geo-api.xg22.top` 已退役** |
| 前端 | 同上域名的 `/` → 容器 `geo-web`（Next standalone，只绑 `127.0.0.1:3000`）。2026-08-11 上线 |
| Caddy | `/etc/caddy/Caddyfile`，**同机还有 fund. / option. 两个别的项目** —— 改完只 `systemctl reload caddy`，勿 restart；改前先备份 |
| 工作树 / 裸仓 | `/opt/geo-demo` · `/opt/geo-demo.git` |
| API | `:8200`（需 Key） |
| 库 | `127.0.0.1:5433`（**勿改 0.0.0.0**；默认口令 `geo/geo` 是弱口令，对外前必须改） |
| 日志 | `/var/log/geo-demo-deploy.log` |
| 容器 | `geo-api` · `geo-web` · `geo-postgres` · `geo-crawler`（**冷备，平时停着**，见 §10.1） |
| tailnet | `sg-dc1` = `100.64.240.17`。postgres 经 `tailscale serve --tcp 5433` 只暴露给 tailnet，**不改 compose 的绑定** |
| 勿碰 | `:8100` sillytavern · `:8090` fund-dashboard · 现有 nginx |

### 10.1 采集在别的机器上（2026-08-14 起）

**`crawler` 不在 VPS 跑了。** 出口 IP 会影响 AI 的回答（已在真实数据上验证：
run 215 vs run 27/54），而 VPS 在新加坡、服务对象是大陆用户、待接的三个平台
（豆包 · 千问 · Kimi）全是大陆服务。所以 crawler 单独跑在一台**大陆家宽**的
节点上，`api` / `web` / `postgres` 仍在 VPS。

| | |
|---|---|
| 部署 / 自检 | `scripts/crawl-node/deploy.sh`（不含凭证，全走环境变量）。**crawler 的代码在镜像里，容器只挂 `/data`** —— 更新代码 = `git push vps main`（VPS 上 build）→ `./deploy.sh all`（重传镜像） |
| 约束与切换 | `scripts/crawl-node/README.md` —— **改任何东西之前先读它** |
| 链路 | 采集节点 ──tailnet──▶ `100.64.240.17:5433` |

四条最容易出事的：

1. **crawler 容器绝对不能走代理。** 走了出口就变成代理的落地，
   数据照样采得到、只是全部来自错误的地理位置，**没有任何地方会报错**。
   `deploy.sh verify` 有一条硬检查：容器出口 ≠ 代理出口。
2. **镜像从 VPS 经 tailnet 传，不在节点上从 mcr 拉**（90 分钟 vs 66 秒）。
3. **VPS 上的 `geo-crawler` 是冷备，只能接替不能并行** ——
   并行会让一次 run 的样本混着两个出口，而数据里没有字段记录是哪台采的。
   2026-08-14 起 `deploy/deploy.sh` 对停止态的它走 `compose create --build`
   （重建但不启动，见 §10.2）；**在那之前每推一次代码都会把冷备静默拉起来** ——
   旧判断是「容器存在就 `up -d`」，而 `docker ps -a` 连停止的容器一起匹配。
4. **截图已恢复**（2026-08-20，P2-34）。节点跑 HTTP worker 模式，截图随
   `POST /v1/worker/jobs/{id}/result` 的 multipart 传回 VPS，由 api 落到自己那边的
   `SCREENSHOT_DIR`。⚠️ **两种模式对这个变量的要求正好相反**：隧道模式必须为空
   （节点写的图 VPS 读不到，留着只会 404），worker 模式必须非空。

### 10.2 部署 hook 是两个文件（2026-08-14 起）

`git push vps main` 仍然**就是上线**，没有闸门（§6 / `PHASE2` §6 不变）。变的是
hook 的结构 —— 从一个文件拆成存根 + 正文：

| | |
|---|---|
| `deploy/post-receive.hook` | **存根**，装在 `/opt/geo-demo.git/hooks/post-receive`。只做「读 stdin 判断 ref → 抢锁 → `checkout -f main` → `exec` 正文」 |
| `deploy/deploy.sh` | **正文**，`docker compose` 那一整套。跟着工作树走，改它不需要碰 hook |

**为什么拆。** bash 是按字节偏移边读边执行脚本的。原来那一个文件里有一句
「refresh hook from repo」，用 `cp` 覆盖了**正在被执行的自己**：新旧长度一不同，
剩下的部分就从错的偏移继续读。已在 VPS 沙箱里复现过 —— 一次 push 只跑完了
checkout，后面 `docker compose up` 和全部健康检查**被静默跳过，而 `git push`
照样报成功**。这是最坏的一类失败：看着上线了，其实什么都没重建。

拆开之后，「正在跑的文件」和「被改写的文件」永远不是同一个：正文在 checkout 阶段
就整份写完，之后才被 `exec` 进去。存根里那把 `flock` 是同一件事的另一面 ——
并发 push 会在上一轮正文跑到一半时把它 checkout 覆盖掉。

**改了存根要手动装。** 正文会在检测到差异时装上新存根，但**下一次 push 才生效**，
且旧的会留一份 `post-receive.prev`。所以改存根的那一次要先手动装再 push：

```bash
PEM=~/Desktop/pem/SG-DC1.pem; VPS=root@100.64.240.17     # 走 tailnet
ssh -i $PEM $VPS 'cp -p /opt/geo-demo.git/hooks/post-receive /root/post-receive.stub-known-good-$(date +%F).bak'
scp -i $PEM deploy/post-receive.hook $VPS:/opt/geo-demo.git/hooks/post-receive
ssh -i $PEM $VPS 'chmod +x /opt/geo-demo.git/hooks/post-receive'
git push vps main
```

**存根坏了 = 之后所有部署都完蛋**，所以恢复手段不能依赖 push（`PHASE2` §6 规矩 1）。
VPS `/root` 下常备副本，直接 `cp` 回去，不需要 `git revert`：

| 文件 | 是什么 |
|------|--------|
| `/root/post-receive.stub-known-good-2026-08-14.bak` | 当前存根的已知可用副本，**首选恢复目标** |
| `/root/post-receive.OLD-monolith-2026-08-14.bak` | 拆分之前那个单文件 hook。⚠️ 它自带本节说的覆盖自己那个 bug，只在需要整体退回旧结构时才用 |
| `$GIT_DIR/hooks/post-receive.prev` | 正文自动装新存根时留下的上一版（存根没变化时不生成） |

```bash
ssh -i $PEM $VPS 'cp /root/post-receive.stub-known-good-2026-08-14.bak /opt/geo-demo.git/hooks/post-receive'
```

**正文里那段 crawler 是有意不启动的。** VPS 上的 `geo-crawler` 是冷备（§10.1 第 3 条），
以前每次部署都会把它 `up` 起来 —— 和大陆节点并行采集，样本混着两个出口而没有任何
字段能事后分开。现在按容器原本的状态走：在跑的 `up`，停着的用 `create` 重建后
**仍然停着**（重建是必要的，否则将来 `docker start` 起来的是旧代码）。

```bash
# 一次性：配置 push 远端
export GIT_SSH_COMMAND='ssh -i <pem> -o IdentitiesOnly=yes'   # pem 需 chmod 400
git remote add vps root@96.9.213.230:/opt/geo-demo.git

# 发布（post-receive 自动 build + up）
git push vps main

# 健康 / 计数（在可访问 API 处）
curl -s -H "X-API-Key: $KEY" http://127.0.0.1:8200/health
curl -s -H "X-API-Key: $KEY" "http://127.0.0.1:8200/v1/counts?brand_id=<id>"

# 建任务
curl -s -X POST http://127.0.0.1:8200/v1/crawl-jobs \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"prompt_id":<id>,"platform":"deepseek","samples":1}'

# 改了 L1 规则后重跑标注（反复跑到 processed=0）
curl -s -X POST -H "X-API-Key: $KEY" \
  'http://127.0.0.1:8200/v1/responses/annotate/run?limit=500'

# 建用户（首个超管也走这里 —— 密码是 argon2 哈希，手写 SQL 生成不了）
# 密码走交互式输入，不接受命令行参数（否则进 shell history 与 /proc/<pid>/cmdline）
docker exec -it geo-api python -m app.scripts.create_user \
  --email you@example.com --role superadmin
# 客户账号必须带 workspace：--role client --workspace-id 2

# 数据治理。⚠️ 注意 --dry-run 是**可选开关**，不加就直接写库（与下面的回填脚本相反）
docker exec geo-api python -m app.scripts.data_governance_min --dry-run

# 历史 job 回填到一个补建的 run（Task/Run 引入前的样本 run_id 为空，新 IA 里不可见）
# 这个脚本**默认只读**，--apply 才写库 —— 它建实体、改外键，比清理脚本危险
docker exec geo-api python -m app.scripts.backfill_run --brand-id 34
docker exec geo-api python -m app.scripts.backfill_run --brand-id 34 --apply

# 自检
docker exec geo-api python -m app.scripts.verify_l2 --brand-id <id>
cd apps/api && PYTHONPATH=. pytest tests/ -q       # 需真库的用例会 skip
cd packages/metrics && pytest -q

# 需真库的用例（在 VPS 容器内跑全套）
docker exec geo-api pip install -q pytest httpx    # 生产镜像不含 dev 依赖，重建后要重装
docker exec -w /app/apps/api -e PYTHONPATH=. \
  -e GEO_TEST_DATABASE_URL="postgresql+psycopg://geo:geo@postgres:5432/geo" \
  geo-api python -m pytest tests/ -q
```

**环境变量要点：** `DATABASE_URL` · `API_KEY` · `CRAWL_MODE=real` · `FAKE_WORKER_ENABLED=false`（真抓）· `DEEPSEEK_STORAGE_STATE` · `SCREENSHOT_DIR` · `CRAWL_STUCK_JOB_SEC`（僵死回收）· `CRAWL_AUTO_RETRY_ENABLED`（自动退避重试，**默认 false**）· `CRAWL_MAX_ATTEMPTS` / `CRAWL_RETRY_BASE_SEC` / `CRAWL_RETRY_MAX_SEC` / `CRAWL_RETRY_JITTER`（§7.2）。

> `CRAWL_AUTO_RETRY_ENABLED` **同时是回滚手段**：出事改环境变量重启 crawler 即可回到
> 「只分类不重试」，不必 `git revert` 重新 build（PHASE2 §6 规矩 1）。

**故障：** 401→Key；pending 不动→crawler/日志；登录墙→storage_state；截图脏→是否 clean-render 镜像；counts 怪→fake/status/别名。

**密钥、pem、storage_state、截图 bulk：禁止进 Git。**

### 10.3 只有一个 main —— 拓扑不进代码，更不进分支

**采集节点上没有 git。** 它跑的是一个**镜像**，那个镜像由 VPS 从 `main` build、
经 tailnet 传过去（`scripts/crawl-node/deploy.sh all`）。所以：

```text
           ┌──────────────── 唯一的真相 ────────────────┐
本机 main ──push──▶ VPS 裸仓 ──build──▶ deploy-api / deploy-web / deploy-crawler
                                              │
                                              └──save|load──▶ 采集节点（只有镜像）
```

**「哪台 crawler 在跑」不是分支，是运行时状态。** 三样东西决定当前拓扑，
全都在代码之外：

| 维度 | 由什么决定 | 在哪看 |
|---|---|---|
| 哪台 crawler 在采 | 容器起没起（VPS 那台是冷备，`Created`/`Exited`） | `docker ps -a` / `podman ps` |
| 出口地理位置 | 容器跑在哪台机器上 + 不设代理 | `deploy.sh verify` 第 ③ 项 |
| 时区 / 重试 / 截图 | 环境变量（`CRAWL_TIMEZONE_ID` 等） | `deploy.sh` 里的 `podman run` |
| 登录态 | 节点 `/data/deepseek_storage.json` | `deploy.sh verify` 第 ① 项 |

#### 为什么不按拓扑开分支

直觉上很想要一条「长沙分支」和一条「新加坡分支」。**别做**，三条理由都硬：

1. **切换出口会变成一次 merge。** 而切换出口本该是 `docker start` / `docker stop`
   —— 冷备存在的全部意义就是几秒钟切过去。
2. **两条分支必然漂移。** 所有与拓扑无关的改动（Provider、API、前端）都要
   cherry-pick 两遍，漏一次就是两套口径。
3. **回滚要动 git。** 而 `PHASE2` §6 规矩 1 写得很清楚：
   **能不用 git 回滚的，就别依赖 git 回滚。** 让危险的东西活在容器编排层。

#### 分支怎么用

一次任务一条短分支 → ff 进 `main` → **删掉**。`main` 永远等于线上
（`git --git-dir=/opt/geo-demo.git rev-parse main` 可核对）。
长期存在的分支只会让人猜「这条是不是还有用」。

> **唯一的 git 远端是生产服务器本身**（`vps` → `/opt/geo-demo.git`）。
> 也就是说仓库历史只存在于本机和那台 VPS 上，**没有异地备份**。
> 这不影响日常，但那台机器没了就只剩本机一份。

---

## 11. 已知债务（现行代码的真实状态，不是待办清单）

| 债 | 现状 | 何时会咬人 |
|----|------|-----------|
| **counts 全量加载** | 把所有 `RawResponse`（含 `full_text` 全文）拉进 Python 再累加，不是 SQL 聚合 | 样本量上千后 |
| **L1 白名单仍缺情感** | `sentiment` / `is_recommended` 恒空（§3.3）；`/v1/counts` 无 `m_recommended` | 前端要情感、推荐率时 |
| `verify_l2.py` 误报 | 改过 `competitor_links` 后，残留的旧 mention 行会让 SQL 侧多出品牌分组，比对报 FAIL | 调整竞品集合后 |
| ~~引用分析做不了~~ **已解决（P2-37）** | 千问的引用走 SSE 流抽取，库里现在有 144 条引用 / 40 个域名；前端已在 `/citations` 用上 | — |
| id=6 残留会话 URL | `raw_json` 里有一条 DeepSeek 会话 URL，违反「不落库会话 URL」（§7）。旧 `chrome_bridge` 路径遗留，一条 UPDATE 可清 | 随时可清 |

---

## 12. 从历史 01–27 里刻意丢掉的东西

历史文档已**全部删除**（`git log` 可找回），要点已提炼进本文。下列内容**刻意不收**：

| 丢弃 | 原因 |
|------|------|
| B1–B7 逐步实施日记、逐步验收表 | 已完成；价值已转化为 §7 的约束与 §4 的 API |
| 一次性治理/验收的执行快照（删了几行 fake、当时 n_valid 是多少） | 数据会变；只保留**结论**与 §6.3 的基线 |
| 本机 Docker 为主路径的叙述 | 现行是 VPS 运行 |
| L3 页面 / IA / g1geo 排版长文 | 属前端产品，另成文档 |
| Playwright 通用教程、截图技术长文 | 只保留「我们怎么取证」的约束（§7） |
| Git 教程长文 | 运维保留 push 必要命令即可（§10） |
| 架构长文、开源项目评估大表 | 背景材料，非现行规格 |
| 完整建表 DDL 与索引建议 | 代码是真相（`entities.py` / `schema.py`）；文档抄一份必然烂掉 |
| M0–M4 迭代计划、P0–P5 落地顺序 | 已走完或已改道 |
| counts 的 `category` 过滤参数设想 | **已拍板不做**（§4） |
| 把 rate 写进 `metric_snapshots` 当权威 | 与分层冲突（§2.1） |
| 多采样众数代表值、Phase 1.5 采样方案 | 未实现，且与「counts only」分层冲突 |

---

## 13. 维护规则

1. 后端规格**只改这一文件**（将来明确拆分时再拆，禁止再长出 01–27）。  
2. **先改代码与测试，再改本文。** 本文描述现状，不描述愿望。  
3. 写进本文的事实必须**当场对着代码核过**；核不动的写进 §11 而不是当成规格。  
4. 数据快照（如 §6.3 基线）必须带日期，且只保留一份最新的。
