# GEO Demo · 前端对接契约

> **给前端看的唯一接口文档。** 字段清单由 `app.openapi()` 导出核对，不是凭记忆写的。
> 后端职责与内部约定见 [BACKEND.md](./BACKEND.md)；两者冲突时**以代码为准**，并回来改文档。
> 在线 schema：`GET /openapi.json` · 交互式：`GET /docs`

---

## 1. 接入信息

| 项 | 值 |
|----|-----|
| Base URL | `https://geo.xg22.top`（与前端**同源**，Caddy 按路径分流到 `geo-api:8200`） |
| 前端 Origin | `https://geo.xg22.top` —— **同一个域名**，前端在 `/`、API 在 `/v1/*` |
| 跨域 | **没有跨域**。同源，无 CORS。`fetch` 仍建议带 `credentials: 'include'`（同源下是默认行为，写明更清楚） |
| 内容类型 | 一律 JSON（登录也是 JSON，不是表单） |

**前端只用一条身份通道：会话 Cookie。** `X-API-Key` 是机器凭证（运维脚本、CI），
**不要打进前端包** —— 它等同超管权限。

---

## 2. 登录与身份

### `POST /v1/auth/login`（公开）

```jsonc
// 请求
{ "email": "you@example.com", "password": "..." }

// 200 → 同时下发两个 Cookie
// geo_session : HttpOnly，JS 读不到（XSS 偷不走）
// geo_csrf    : 非 HttpOnly，**前端要读它**，见 §2.1
{ "user_id": 1, "email": "you@example.com", "role": "operator",
  "workspace_id": null, "kind": "user",
  "csrf_token": "…" }   // ← 写操作要用它，见 §2.1
```

**登录失败一律 401 且只有一句话** —— 不区分「用户不存在 / 密码错 / 账号停用」，
所以前端也**不要**据此给出「该邮箱未注册」这类提示，那等于把账号枚举接口做到 UI 上。

### `GET /v1/auth/me`

返回同上结构。**前端据此渲染菜单与按钮，但权限判断始终在服务端** ——
前端隐藏按钮只是体验，不是安全边界。

| 字段 | 说明 |
|------|------|
| `role` | `superadmin` \| `operator` \| `client` |
| `workspace_id` | **只有 client 非空**，是他能看到的品牌范围 |
| `kind` | `user`（会话）\| `machine`（共享密钥 / QA 后门） |

### `POST /v1/auth/logout` → 204，清两个 Cookie

### 2.1 CSRF（**当前默认关闭**，前端就绪后开）

写操作要把 token 放进 `X-CSRF-Token` 请求头。

**token 从响应体拿。** `login` 与 `me` 的响应体里都有 `csrf_token`，
存内存即可（**别进 localStorage**）。

同源之后 `document.cookie` 其实也读得到 `geo_csrf` 了，但**仍然走响应体** ——
它不依赖 Cookie 作用域，将来若再变拓扑不用改前端。

```ts
// 登录时拿到；刷新页面后从 GET /v1/auth/me 重新拿
const { csrf_token } = await login(email, password)

fetch(url, { method: 'POST', credentials: 'include',
             headers: { 'X-CSRF-Token': csrf_token, 'Content-Type': 'application/json' } })
```



> **开关已于 2026-08-11 打开。** 没带 `X-CSRF-Token` 的会话写操作现在一律 403，
> 响应 detail 会说清缺什么。
>
> 只影响「用户会话 + 写方法」这一条通道：`X-API-Key` 走机器通道不过 CSRF，
> `/qa` 后门 Cookie 只对安全方法生效，两者都不受影响。
> `POST /v1/auth/login` 在公开路径里 —— 登录前拿不到 token，自然不能要求它。

### 2.2 状态码约定

| 码 | 含义 | 前端该做什么 |
|----|------|-------------|
| **401** | 未登录 / 会话过期 | 跳登录页 |
| **403** | 已登录但没权限，或 CSRF 校验失败 | **不要跳登录页** —— 会陷入登录循环。提示「无权限」 |
| **404** | 不存在**或不属于你** | 二者对外不可区分（防枚举）。当作「没有这条」处理 |

---

## 3. 角色能力

| 能力 | 超管 | 运营 | 客户 |
|------|:---:|:---:|:---:|
| 看数据（counts / responses / 截图） | 全部 | 全部 | **仅本 workspace** |
| 品牌 / 别名 / 竞品 / 提问词 增改删 | ✓ | ✓ | ✗ |
| 发起抓取、重试、重标注 | ✓ | ✓ | ✗ |
| 用户管理 `/v1/users` | ✓ | ✗ | ✗ |

**客户是纯只读**，且**列表接口会被自动收敛**到他的 workspace ——
前端不必也不应该自己加过滤。唯一例外：`/v1/crawl-jobs` 对客户
**必须传 `prompt_id` 或 `run_id`**，否则 400（任务列表本身会泄露别家在监测什么）。

---

## 4. 指标接口（前端算比率的唯一数据源）

### `GET /v1/counts`

| 参数 | 必填 | 说明 |
|------|:---:|------|
| `brand_id` | ✓ | 监测主品牌 |
| `platform` | | 如 `deepseek` |
| `prompt_id` | | |
| `run_id` | | **同时把竞品集切到该 run 的快照**，见 §8.5.2 |
| `from` / `to` | | ISO 日期或时间；`to` **含当天末**（纯日期自动补到 23:59:59） |
| `group_by` | | `none`(默认) \| `day` \| `platform` \| `prompt` \| **`search_used`** |
| `include_fake` | | 默认 `false` |
| `source` | | 如 `deepseek_web` |

```jsonc
{
  "brand_id": 34,
  "filters": { /* 回显 */ },
  "group_by": "none",
  "denominator": {
    "definition": "answer_status=ok",
    "n_valid": 35,            // ← 分母，只有这一个
    "n_total_responses": 35,
    "n_empty": 0, "n_too_short": 0, "n_error": 0, "n_unannotated": 0
  },
  "brand":       { "brand_id": 34, "m_mentioned": 21, "m_body": 21,
                   "m_citation_only": 0, "m_none": 14,
                   "m_head": 15, "m_middle": 5, "m_tail": 1,
                   "m_first": 6 },        // ← position_rank == 1 的样本数
  "competitors": [ /* 同结构 × N */ ],
  "series":      [ /* group_by ≠ none 时：{ key, denominator, brand, competitors } */ ]
}
```

**全是整数，永远不返回比率。**

#### `group_by=search_used`：按联网标注分桶（P2-37）

`series[].key` 是 **三个字符串**：`"true"` / `"false"` / **`"unknown"`**。

⚠️ **`unknown` 不是「没联网」，是「我们不知道」** —— P2-37 之前采的样本
（库里有 55 条）全落在这一桶。把它并进 `false` 去算「未联网占比」，
就是在报告里凭空断言一件没测过的事。

**三桶不重不漏地覆盖全集**：`Σ series[].denominator.n_valid == denominator.n_valid`，
所以三桶的占比能加到 100%。用例钉着这条。

### 4.1 前端自己算

```ts
提及率      = m_mentioned / n_valid
首位提及率  = m_first / m_mentioned        // 分母是「被提及的样本」，不是 n_valid
头部占比    = m_head / m_mentioned
SoV         = m_本品 / (m_本品 + Σ m_竞品)
分母为 0 → 显示「—」，不要显示 0%
```

**`m_first` 不是「首推率」。** 它数的是 `position_rank == 1`，即「在被监测品牌里
最先出现」的位置事实（口径见 §7.1）。叫成「首推」是拿措辞夸大结论 ——
我们不知道 AI 推没推荐它，只知道它先被提到。

### 4.2 四个必须记住的坑

1. **任意时间窗一律 `Σm / Σn`，绝不能把日比率求平均。** 分母不等时两者不相等，
   平均出来的数字没有任何口径。这是「后端只给整数」的根本理由。
2. **`group_by=prompt` 的 `series[].key` 是 prompt_id 字符串，不是提问文案。**
   行标题要自己去 `/v1/prompts` 关联。`group_by=day` 的 key 是 **UTC 日期**。
3. **`competitors[]` 按 `brand_id` 关联，不许按数组下标** —— 顺序不保证。
4. **凡显示比率，必须同时显示 `m / n`。** 孤零零的百分比在这个产品里没有可信度。

### `GET /v1/citations/domains` —— 哪些站正在被 AI 引用（P2-37 之后）

参数与 `/v1/counts` 同套：`brand_id`(必填) · `platform` · `prompt_id` · `run_id` ·
`from`/`to` · `limit`(≤200)。

```jsonc
{
  "n_citations": 147, "n_domains": 38,
  "items": [
    { "domain": "www.bitauto.com", "n_citations": 23, "n_samples": 6 },
    { "domain": "36kr.com",        "n_citations": 9,  "n_samples": 8 }
  ]
}
```

**口径：按引用次数累加** —— 一个域名在一条回答里被引 3 次就计 3。

⚠️ **`n_samples` 是诊断字段，不参与排序。** 这个口径对聚合型站点有偏向：
上例里 bitauto 23 次只来自 6 条样本，而 36kr 9 次分布在 8 条样本 ——
**后者的覆盖面其实更广**。没有 `n_samples` 的话这两行在榜单上只能比大小。

**只数 `answer_status='ok'` 的样本**，与 `/v1/counts` 共用同一个分母定义 ——
这个项目只允许有一个分母口径，让引用榜单跑在另一套样本集合上，
等于同一个页面上两个数字来自两个宇宙。

---

## 5. 配置接口（防前端硬编码）

### `GET /v1/config/platforms` ← **平台 chip 必读这个**

```jsonc
{ "crawl_mode": "real",
  "items": [
    { "code":"deepseek", "label":"DeepSeek", "available":true,  "implemented":true,  "note":null },
    { "code":"doubao",   "label":"豆包",     "available":false, "implemented":false, "note":"Provider 未实现" }
  ] }
```

- `available` = **现在建任务能不能跑完** → 决定 chip 可点还是灰显
- `implemented` = 有没有 real Provider → 与 available 分开，便于区分「没接」和「在跑假数据」
- **不要硬编码平台清单**。接第二个平台时后端改一行，前端零改动

### `GET /v1/config/metrics`

`answer_status_values` / `mention_types` / `position_buckets` /
`default_composite_weights` / `annotator_version` / `crawl_mode_default_hint`。
口径文案从这里取，别在前端写死枚举。

---

## 6. 配置数据

### `GET /v1/brands` → `{ items: BrandOut[], total }`

`BrandOut`：`id` · `workspace_id` · `name` · `name_en?` · `industry?` ·
**`aliases: string[]`** · **`competitor_ids: number[]`** · `created_at`

> 竞品**也是 brand 行**，不是字符串。矩阵列顺序建议按 `competitor_ids` 定。

### `GET /v1/prompts?brand_id=&active_only=`

`PromptOut`：`id` · `brand_id` · `text` · `category?` · `tags[]` · `is_active` · `created_at`

> `category`（`unprompted` / `scenario`）**没有服务端过滤参数** —— 拿回来自己归类。

### 写操作（仅超管/运营）

| 方法 | 路径 | 备注 |
|------|------|------|
| POST | `/v1/brands` | `workspace_id` 必填 |
| PATCH / DELETE | `/v1/brands/{id}` | |
| PUT | `/v1/brands/{id}/aliases` | **整体替换**，先读全量再提交 |
| PUT | `/v1/brands/{id}/competitors` | **整体替换** id 列表 |
| POST / PATCH / DELETE | `/v1/prompts`（`/{id}`） | |

---

## 7. 样本与证据

### `GET /v1/responses`

参数：`platform` · `prompt_id` · `brand_id` · **`run_id`** · `answer_status` ·
`limit`(≤200) · **`offset`**

```jsonc
{ "items": [RawResponseOut], "total": 50 }   // total 是过滤后全量，不受分页影响
```

`RawResponseOut`：`id` · `job_id` · `platform` · `prompt_text` · **`full_text`** ·
`screenshot_path?` · `raw_json?` · `latency_ms?` · `answer_status?` ·
`annotator_version?` · `created_at` · `citations[]` · `mentions[]`

> ⚠️ **每一行都带完整 `full_text`**，外加 `raw_json`（里面往往还有一份同样的正文）。
> **列表场景一律用下面的 `/v1/responses/summary`**；这个端点留给「要看某一条的全文」。

**`run_id` 的口径与 §8.5.2 的快照一致**：`?run_id=128` 列的就是这一次运行的样本，
不带它列的是该品牌历史所有运行混在一起的。任务详情页的样本列表必须带它 ——
理由和 KPI 必须带 `run_id` 是同一条。客户也能用这个参数（不属于自己的 run 一律 404）。

#### `search_used`：联网标注是**三态**（P2-37，2026-08-21 起）

```jsonc
"search_used": true    // 这次联网了
"search_used": false   // **确认**没联网 —— 品牌对比类提问的常态
"search_used": null    // **我们不知道**：迁移前的老样本 / 别的平台 / 解析失败
```

⚠️ **`null` 不是 `false`，前端分桶时必须单独一桶。** 把 `null` 并进「没联网」
就是把「没记」说成「没联网」—— 而这一列的用途正是分桶报告，分错桶等于多一条假结论。
（与 P2-36「探不到就留 NULL，不编默认值」同一条规矩。）

**口径**（`PHASE2.md` §4.0.1）：**不强制开联网**。三家里只有 DeepSeek 有开关，
而且我们的监测集是品牌对比类提问，**本来就不触发联网**（时效性问题才触发）。
学术侧明确反对丢弃未联网样本（选择偏差）——
「**记录 search 是否激活；无搜索输出是结果，不是废样本**」。

千问的 `search_used` 与 `citations` 都来自 **SSE 流**，不是 DOM ——
DOM 里一条外链都没有。来源列表里那些 `Citation` 表装不下的字段
（站点名 `name`、发布时间 `publish_time`）原样留在 `raw_json.sources` 里。

### `GET /v1/responses/summary` ← **列表页用这个**

参数与 `GET /v1/responses` **逐字一致**（含 `run_id`），换端点不必换查询拼装。

```jsonc
{ "items": [RawResponseSummaryOut], "total": 35 }
```

`RawResponseSummaryOut`：`id` · `job_id` · `platform` · `prompt_text` ·
**`text_preview`**（正文前 160 字）· **`text_length`**（正文总字数）·
`screenshot_path?` · `latency_ms?` · `answer_status?` · `annotator_version?` ·
`created_at` · `mentions[]`

**没有 `full_text`，也没有 `raw_json`** —— 不是「有时没有」，是这个模型里就没这两个字段，
所以类型上可以放心当它们不存在。要全文走 `GET /v1/responses/{id}`。
截断发生在数据库那侧（`substr`），大列根本不过网。

`text_length > text_preview.length` 就是「这条被截断了」—— 拿它做「查看全文」的入口判断，
别去数 preview 的字数。

### `MentionOut` —— 逐品牌的 L1 标注

| 字段 | 说明 |
|------|------|
| `mentioned` / `mention_type` | `body` \| `citation_only` \| `none` |
| `position_bucket` | `head` / `middle` / `tail`，按首次提及 offset 三等分 |
| **`position_rank`** | 出场顺位（1-based）。**是位置事实，不是推荐名次**，见 §7.1 |
| **`first_offset`** | 首次命中在 `full_text` 里的下标 |
| **`matched_term`** | 实际命中的原文片段（保留原大小写） |
| `evidence_snippet` | 命中处前后各 40 字 |
| `sentiment` / `is_recommended` | **当前恒空**，见 §9 |

### 7.1 高亮：一条可自检的不变量

**`first_offset` 是「码点」索引，不是 JS 的 UTF-16 单元索引。**

```python
# Python（后端口径，成立）
full_text[first_offset : first_offset + len(matched_term)] == matched_term
```

```ts
// JS：**不能**直接用 String.slice —— 它按 UTF-16 单元切，
// 一个 🏃 在 Python 里算 1、在 JS 里算 2，正文有一个 emoji 就开始错位
const cp = Array.from(full_text)               // 按码点拆
cp.slice(first_offset, first_offset + Array.from(matched_term).length).join('') === matched_term
```

> **这里原来写的是 `full_text.slice(...)`，那个写法在 JS 里是错的。**
> 后端在全库 179 条上验过 179/179 —— 那是 Python 侧的验证，成立；
> 错的是「前端可以照抄这个表达式」这个假设。
>
> 2026-08-12 由部署后冒烟在生产数据上抓到：某条回答含 4 个 emoji
> （810 码点 / 814 UTF-16 单元），`Nike` 被切成了 `如Nik`。前端的自检
> 拦住了它（对不上就不画、改报告警），所以没有画错，但含 emoji 的回答
> 一律没有高亮。修法见 `apps/web/src/lib/l3/evidence.ts`。

`first_offset` 非空时这条**必然成立**。前端应当 assert 它，错位会立刻暴露。

**禁止**自己拿 `matched_term` 去 `full_text` 里 `indexOf` —— 会和 L1 标注口径分叉
（大小写折叠、别名优先级规则都在后端）。

**`position_rank` 的口径**：正文命中的品牌按 `first_offset` 升序排名，
只在**被监测品牌集合内**排。回答里先提到未监测的品牌时，我方 `rank=1` 仍是 1 ——
含义是「我们关心的品牌里它最先出现」，**不是「AI 首推我们」**。
`citation_only` 是 `null`（正文没出现），不是排最后。

### `GET /v1/media/screenshots/{basename}`

`RawResponseOut.screenshot_path` **已经是 basename**，直接拼即可：

```html
<img src="https://geo.xg22.top/v1/media/screenshots/deepseek_1785601999.png">
```

跨站 `<img>` 会自动带上会话 Cookie（`SameSite=None; Secure`）。
响应带 `Cache-Control: private, no-store`，**不要在前端缓存它**。

---

## 8. 任务

### `GET /v1/crawl-jobs`

参数：`status` · `platform` · `prompt_id` · **`run_id`** · `limit`(≤200) · **`offset`**

`CrawlJobOut`：`id` · `prompt_id` · `platform` · `status` ·
**`sample_index`**（同一 prompt 的第几次采样）· `error_message?` ·
**`failure_kind?`** · **`attempt?`** · **`next_attempt_at?`** ·
`started_at?` · `finished_at?` · `created_at` · **`response_id?`**（可直接下钻）

`status`：`pending` → `running` → `success` / `failed`

#### 8.0.1 失败分类 `failure_kind`

| 值 | 含义 | 自动重试 |
|---|---|---|
| `timeout` | 超时（冷启动被限流最常见的表现） | ✅ |
| `rate_limited` | 明确的限流信号（429 / 「访问过于频繁」） | ✅ |
| `login_required` | `storage_state` 过期，要人去换 | ❌ |
| `platform_unavailable` | Provider 没实现 | ❌ |
| `parse_error` | 拿到页面了但抽不出答案（DOM 可能变了） | ❌ |
| `worker_died` | 僵死回收收的，worker 中途没了 | ❌ |
| `unknown` | 没认出来 | ❌ |

**`null` 表示「还没失败过」，不表示「失败了但没认出来」** ——
后者是 `unknown`。两者的排查方向完全不同，别在前端把它们显示成同一个词。

#### 8.0.2 退避中的 job 状态仍是 `pending`

自动重试（P2-16）不新增状态值。一条正在等退避的 job 是 `pending` +
`next_attempt_at` 在未来；一条还没轮到的 job 是 `pending` + `next_attempt_at`
为 `null`。**要区分只能看这个字段**，`status` 上它们一模一样。

这直接影响 run 状态：重试期间那次 run 是 `running` / `pending`，
**不是 `partial`** —— 还没定论。所以自动刷新会多转一会儿
（默认曲线 30s → 60s，最多约 90 秒）。

`attempt` 是已消耗的尝试次数。**`attempt > 1` 且 `status='success'`
就是「重试之后成功的」** —— 没有另一张表记重试历史，这个组合就是全部信号。

> 客户**必须传 `prompt_id` 或 `run_id`**，否则 400（见 §3）。两个都不属于自己时 404。

**失败的采样只在这里看得见。** 失败的 job 没产出 `RawResponse`，
所以它在 `/v1/responses` 里根本不出现 —— 想知道「这次运行还有几条没回来」，
用 `?run_id=128&status=failed` 取 `total`。
`partial` 状态的 run 上，这个数就是分母少掉的那一截。

### `POST /v1/crawl-jobs`（仅超管/运营）

```jsonc
{ "prompt_id": 23, "platform": "deepseek", "samples": 3 }  // → 返回 3 个 job
```

**未接入的平台会 400 并列出当前可用平台** —— 不会先建成功再默默失败。

### `POST /v1/crawl-jobs/{id}/retry`

`failed` / `success` / `running` 都可重排（`running` 是为了救僵死任务）。

**它同时把自动重试的计数清零**（`attempt` / `failure_kind` / `next_attempt_at`）。
人点这个按钮意味着他做了判断 —— 换了 `storage_state`、限流过去了 ——
所以重试预算重新给。不清零的话，一条已耗尽次数的 job 手动重排后再失败一次
就直接终态，按钮只生效一半。

---

### `GET /v1/health/credentials`（仅超管/运营）

登录态健康度（P2-07）。**不含任何 cookie 的值** —— 只有名字、域、过期时间。

```jsonc
{
  "overall": "mismatch",          // 所有平台里最严重的；一条都没上报过 = "unreported"
  "generated_at": "2026-08-15T...",
  "items": [{
    "platform": "deepseek",
    "status": "mismatch",         // ok | aging | expired | mismatch | missing
    "node_label": "changsha-home",
    "issuer_region": "overseas",  // cn | overseas | unknown  ← 最关键的字段
    "waf_kind": "aws",
    "cookie_count": 4,
    "cookie_names": ["aws-waf-token", "ds_session_id", "smidV2"],
    "earliest_expiry": "2026-08-04T...",
    "file_mtime": "2026-08-12T...",
    "issues": ["签发地是 overseas（aws WAF），而采集出口期望 cn —— IP 切了、环境没切",
               "最早过期的 cookie 已过期 11 天"],
    "checked_at": "2026-08-15T...",
    "last_success_at": "2026-08-15T..."
  }]
}
```

**`issuer_region` 是这里唯一能提前发现问题的字段。** DeepSeek 的境内与境外流量
走两套不同的基础设施，WAF cookie 的名字直接把签发地写在脸上
（`HWWAFSES*` = 华为云 = 境内，`aws-waf-token` = AWS = 境外）。
拿境外签发的登录态在大陆采集，就是「IP 切了、环境没切」。

**`last_success_at` 不够用，别只看它。** 2026-08-15 那次故障里它一直是
「几分钟前」—— 抓取确实在成功，只是每次 run 头几条卡在 WAF 挑战上超时。
**它只能发现「全红」，发现不了「悄悄降级」。**

**⚠️ `earliest_expiry` 只统计「长效」cookie（P2-39，2026-08-20 起）。**

判据是**签发寿命**（`expires − file_mtime`），不是「还剩多久」：
`mtime < expires ≤ mtime + 7 天` 的算短命辅助 cookie，不参与判断，
只在 `ephemeral_expired` 里计数。

在此之前这个字段取的是「最早过期的**任何**一个 cookie」，于是
**千问天天在成功抓取却一直报 `expired`** —— 抓到的是 `alipay` / `xlly_s`
这类签发时只给了几小时到几天的辅助 cookie。节点实测：千问 87 个 cookie 里
已过期的 8 个签发寿命是 0.02–3 天，而真正扛登录的是 **180 天**。

**「短命」必须是正的寿命。** 到期时间早于文件 mtime 的 cookie 签发寿命为负，
它**不是**短命辅助 cookie，而是「导出这份登录态时它就已经死了」——
那正是 2026-08-15 事故的形状，是最响的一个信号，仍然照报。

三个容易看错的地方：

- **`overall: "unreported"` 不是 ok** —— 那表示 crawler 从没上报过
  （老版本，或压根没在跑）。没有数据不等于健康。
- **`issuer_region: "unknown"` 不会被判成 `mismatch`** —— 认不出来就不下结论。
  接新平台时它一开始就是 unknown，那是正常的。
- **`checked_at` 自己也是信号** —— api 读的是 crawler 写的快照，不是实时检查。
  太旧说明 crawler 没在跑。

---

## 8.6 采集节点端点 `/v1/worker/*`（P2-34，仅超管/运营）

**给采集节点用的，前端一条都不该调。** 节点原先直连数据库（`DATABASE_URL`
走 tailnet 到 VPS 的 postgres），这组端点是那条链路的替代：节点只出站 HTTPS。

> **鉴权复用现有 `X-API-Key`**（2026-08-18 拍板）。代价写在 `BACKEND.md` §7.6：
> `X-API-Key` 折算成 **superadmin**，所以节点持有的是超管等价凭证 ——
> P2-34 换掉的是凭证的**形态**（数据库口令 → API key），不是它的**权限面**。

### `POST /v1/worker/lease`

```jsonc
// POST /v1/worker/lease?batch_size=1&environment_id=41
{
  "jobs": [{
    "job_id": 3512,
    "platform": "tongyi",
    "sample_index": 1,
    "prompt_id": 88,
    "prompt_text": "国产运动鞋品牌有哪些值得买的？",
    "brand_names": ["安踏", "ANTA", "安踏体育"]   // 中文名 · 英文名 · 全部别名
  }]
}
```

四条：

- **是 `POST` 不是 `GET`。** 领取会把 job 标成 `running` —— 那是写操作，而中间件
  对安全方法认 `geo_qa_key` Cookie。做成 GET 就是一个跨站诱导一发就能把一批 job
  打成空转（600 秒后被僵死回收成 failed）的口子，攻击方连响应都不用读。
- **`prompt_text` 与 `brand_names` 必须随 payload 下发** —— 节点没有数据库，
  这两样它自己查不到。少给一样，「节点不碰库」就不成立。
- **空 `jobs` 是正常状态**，不是错误。节点每几秒来问一次，多数时候没活干。
- **`environment_id` 不传就不打标记**（P2-36 的语义：留 NULL 表示「没记」，
  比编一个默认值准确）。它由节点先调 `POST /v1/worker/environment` 换取。

领取沿用 `services/crawl_jobs.claim_pending_jobs` 的 `FOR UPDATE SKIP LOCKED`
（本来就是多 worker 安全的），**没有另造一套 SQL**；退避闸门（`next_attempt_at`）
与僵死回收（`CRAWL_STUCK_JOB_SEC`）都照旧生效。

### `POST /v1/worker/jobs/{job_id}/result` ← **multipart，不是 JSON**

```bash
curl -X POST "$API/v1/worker/jobs/3512/result" -H "X-API-Key: $KEY" \
  -F 'payload={"full_text":"国产运动鞋里安踏值得买……","latency_ms":27000,
                "citations":[{"url":"https://example.com/a","cite_index":1}],
                "raw_json":{"provider":"qianwen"}}' \
  -F 'screenshot=@shot.png;type=image/png'      # ← 可选
```
```jsonc
// 响应 200
{ "job_id": 3512, "response_id": 9101, "status": "success" }
```

正文放在 `payload` 表单字段里（`WorkerResultIn` 的 JSON），**截图是可选的第二个
part**。做成 multipart 就是为了截图 —— 迁到大陆节点之后它一直关着
（`SCREENSHOT_DIR=` 置空），因为写在节点本地的图 VPS 读不到、留着只会让证据页 404。
随结果传回来，这笔债才还上。

截图那一侧三条硬规矩：

- **文件名一律服务端生成**（`{platform}_{job_id}_{时间戳}_{随机}.png`），
  **绝不使用节点给的那个** —— 它会被拼进落盘路径，也会成为
  `/v1/media/screenshots/{basename}` 的一段。
- **按魔数判是不是 PNG，不信 `content-type`**（节点随口说的），否则 `415`。
- **超过 `SCREENSHOT_MAX_BYTES`（默认 8MB）直接 `413`**。没有上限的话，
  一个跑飞的节点就能把 VPS 的盘写满，而那块盘上还有数据库。
- 不带 screenshot part 照样落样本，`screenshot_path` 留空 ——
  证据页那个按钮是条件渲染的，**降级是干净的**。

落样本 + 引用 + 收尾 + 跑 L1 标注，走的是**和隧道模式同一个**
`crawl_runner.persist_result`。三条：

- **重复提交是安全的，而且必须安全。** 已经有样本就回**同一个** `response_id`，
  不建第二条。节点在大陆家宽、api 在新加坡，「库里写成功了但 200 没回到节点」
  是必然会发生的形态，节点重试是对的做法 —— 不幂等的话一次抖动就多一条样本，
  而样本直接进 KPI 分母。
- **请求体里没有 `prompt_text`，也没有 `platform`。** 那是建 job 时就定下的事实，
  服务端自己查。让节点回传等于给证据页开一个可以说谎的口子。传了也会被忽略。
- `domain` 不传就由 `url` 推出来。

### `POST /v1/worker/jobs/{job_id}/fail`

```jsonc
// 请求
{ "reason": "等答案超时：正文 0 字符（停止回答按钮=True）", "kind": "timeout" }
// 响应 200：完整的 CrawlJobOut
```

- **`kind` 由节点算好带上来。** `classify_failure` 的判定顺序是
  「异常类型 → 消息模式 → unknown」，而**异常类型过不了 HTTP** ——
  只传字符串的话 `QianwenLoginRequired` 这类会退化成靠中文子串猜。
  取值必须是 `API.md` §8.0.1 那七个之一，**乱写直接 422**（写进库不会有任何地方报错，
  却会静默毁掉重试决策）。不传则退回服务端按消息文本分类。
- **只在 job 还是 `running` 时才真的收。** 重复提交、或已被僵死回收的，
  一律原样返回不再动 —— `attempt` 是重试预算，多扣一次就少试一次。
- 回的是完整 `CrawlJobOut`，节点据此知道这条**会不会被自动重排**
  （`status='pending'` 且 `next_attempt_at` 在未来 = 正在退避）。

### `POST /v1/worker/environment`

```jsonc
// 请求：P2-36 的六个维度
{ "node_label": "changsha-home", "exit_ip": "120.228.64.174",
  "timezone_id": "Asia/Shanghai", "crawl_mode": "real",
  "credential_region": "cn", "waf_kind": "huawei" }
// 响应 200
{ "environment_id": 41 }     // null = 这轮记不上，**不阻断采集**
```

- **请求体里没有 `fingerprint`，服务端自己算。** 指纹定义「什么算同一种环境」——
  让节点上报的话，节点与冷备一旦版本不齐，同一种环境会算出两个指纹，造出一个
  幻影环境，而 P2-36 的告警会据此说「这次 run 混了两个出口」。
  **告警撒谎比没有告警更糟**（P2-39 记着的正是这类问题）。
- 同一种环境**只会有一行**，节点每 `CRAWL_CREDENTIAL_CHECK_SEC` 报一次也不会堆。
- 拿到的 id 带在后续 `POST /v1/worker/lease?environment_id=` 上，
  在**领取那一刻**打到 job 上 —— 与隧道模式语义完全一致。

### `POST /v1/worker/credentials`

```jsonc
// 请求
{ "items": [{
    "platform": "tongyi", "status": "ok", "node_label": "changsha-home",
    "issuer_region": "unknown", "waf_kind": "none",
    "cookie_count": 12, "cookie_names": ["cna", "tfstk"],
    "earliest_expiry": "2026-09-01T00:00:00Z",
    "file_mtime": "2026-08-16T10:00:00Z", "issues": []
}]}
// 响应 200
{ "accepted": 1 }
```

判级（`inspect_storage_state` + `derive_status`，都是纯函数）**在节点上算** ——
`storage_state` 文件在那儿，api 读不到。这里只落库，走的是和隧道模式同一个
`credential_health.store_report`。三条：

- ⚠️ **请求体里没有任何字段能放 cookie 的值。** 这条红线在 schema 上就闭死了，
  节点硬塞也塞不进来。
- **也没有 `checked_at`，由服务端盖章。** 它是「多久没听到节点动静」的信号
  （§7.3），用节点的时钟，钟一歪这个信号就说假话。
- `platform` 与 `status` 都校验取值，**乱写直接 422**：
  platform 是主键（写错就多一行永远清不掉的假平台），
  而不认识的 status 会被 `worse_of` 当成「比 ok 还轻」，
  让一个坏掉的凭证显示成健康。

---

## 8.5 检测任务与运行

**任务（Task）= 命名的监测定义**（一个主品牌 + 平台 + 采样数），可反复执行。
**运行（Run）= 一次执行**。`crawl_jobs` 挂在 run 下面。

| 方法 | 路径 | 备注 |
|------|------|------|
| GET / POST | `/v1/tasks` | 列表按 workspace 自动收敛；建任务仅超管/运营 |
| GET / PATCH | `/v1/tasks/{id}` | PATCH **不含 `brand_id`** —— 任务过不了户 |
| GET | `/v1/tasks/{id}/runs` | 该任务的执行历史 |
| POST | `/v1/tasks/{id}/runs` | 发起一次运行，仅超管/运营。**body 可选**：`{ "note": "…" }` 记这一次的口径说明 |
| GET | `/v1/runs/latest` | **我能看到的最新一次运行**。客户首页分流用；一次都没有时 404 |
| GET | `/v1/runs/{id}` | 带口径快照 |

`TaskOut`：`id` · `brand_id` · `name` · `platforms[]` · `samples` · `is_active` ·
`created_at` · `latest_run_id?` · `latest_run_at?` · `latest_run_status?`

`RunOut`：`id` · `task_id` · `platforms[]` · `note?` · `created_at` · **`status`** · `n_jobs`

`RunDetailOut` = `RunOut` + **`prompts[]`**（`prompt_id` + `prompt_text`）
+ **`competitors[]`**（`competitor_brand_id` + `brand_name`）
+ **`environments[]`** + **`n_jobs_unstamped`**（P2-36，见 §8.5.3）

**`run.note` 怎么写进去**：只能在 `POST /v1/tasks/{id}/runs` 时带，
**没有事后修改的接口**（`/v1/runs/{id}` 只有 GET）。

```jsonc
POST /v1/tasks/27/runs
{ "note": "采集出口已迁至大陆；本次未采集截图" }   // body 整个可选，不带也行
```

口径说明写在发起那一刻，是因为**那时才最清楚这次和以往有什么不同**；
事后补要么忘、要么补的是回忆。它是「这一次的口径和别的不一样」的唯一落点 ——
换了采集出口、关了截图、换了标注器版本，都该写在这儿，
否则趋势图上那个跳变以后没人解释得了。

### 8.5.3 采集环境：这次是在什么条件下采的（P2-36）

```jsonc
"environments": [{
  "environment_id": 3,
  "fingerprint": "changsha-home|120.228.64.174|Asia/Shanghai|real|cn|huawei",
  "node_label": "changsha-home",
  "exit_ip": "120.228.64.174",
  "timezone_id": "Asia/Shanghai",
  "crawl_mode": "real",
  "credential_region": "cn",     // 登录态从哪儿签发的
  "waf_kind": "huawei",
  "n_jobs": 20                   // 这次运行里有多少条样本出自这个环境
}],
"n_jobs_unstamped": 0
```

**`environments.length > 1` 就是混了两个出口** —— 那样这次 run 的数字
不能当成一个整体看，比率是两种条件下的样本硬凑出来的。

冷备「只接替不并行」是一条纪律，而纪律需要证据。2026-08-14 那次部署
把 VPS 冷备静默拉起来跑了 4 小时，当时**没有任何办法事后确认那段时间
有没有混采** —— 这个字段就是为了让那个问题有答案。

**`n_jobs_unstamped` 不是缺陷。** 本功能上线（2026-08-15）之前的所有 run
都会等于 `n_jobs`：当时确实没记。给历史数据编一个「默认环境」等于伪造。

⚠️ **跨 run 比数字之前先比 `fingerprint`。** 指纹不同的两次运行，
差异里混着环境变化 —— run 215 / 292 / 293 之间出口 IP、时区、登录态签发地
全都不一样，而那三次的品牌构成差异一度被当成「出口影响回答」的证据。

---

### 8.5.1 `status` 是算出来的，不是存的

`runs` 表**没有 status 列**，它由该 run 下 job 的状态派生：

```text
empty    一条 job 都没有（提问集为空或平台为空）—— 是配置问题，不是成功
pending  还有 job 没开始
running  有 job 正在跑（优先于 pending）
success  全部成功
partial  部分成功  ← 单独一档
failed   全部失败
```

**`partial` 不能当成 success 显示。** 部分成功意味着分母少了一截，
所有比率会静默偏高。

### 8.5.2 快照：为什么两次 run 之间的差异是可信的

`RunDetailOut` 里的 `prompts` 和 `competitors` 是**发起那一刻冻结的**，
不是实时查的。提问词正文改了、竞品集加人了，都不会回头改写历史运行。

**这直接影响你怎么调 counts：**

```text
/v1/counts?brand_id=34&run_id=128   这一次运行的数（竞品集取自该 run 的快照）
/v1/counts?brand_id=34              该品牌历史累计（竞品集用当前配置）
```

任务详情页的 KPI 必须带 `run_id`。不带的话算的是这个品牌所有 run 混在一起的数，
而且用的是当前竞品集——两次打开会因为别人改了配置而变。

---

## 9. 后端**现在给不了**的（前端要走降级态，不是空态）

| 缺什么 | 影响 | 前端怎么办 |
|--------|------|-----------|
| `sentiment` / `sentiment_score` 恒 `NULL` | 情感 pill、正面率、风险问题 | 显示「暂无情感数据」 |
| `is_recommended` 恒 `False`，counts 无 `m_recommended` | 推荐率 | 算不出，不要做这个指标 |
| **`citations` 全库 0 行** | 引用分析整页 | **这页现在做不了**。根因是抓取时从未开联网搜索，不是解析 bug；要做需先开联网 + 重抓（会破坏现有基线可比性） |
| 只有 DeepSeek 一个平台 | 多平台对比 | 维度留着，可用性读 `/v1/config/platforms` |
| counts 无**顺位分布**（只有 `m_first` 这一个计数） | 命中矩阵格里的 `#N`（该品牌在这几次采样里的中位出场顺位） | 矩阵格**只显示 `m/n`，不显示 `#`**。设计稿本来就允许省掉它 —— 拿 `m_first` 反推名次是编数据 |

> **降级态 ≠ 空态。** 「没采到数据」和「这个维度后端还没算」要用不同文案，
> 否则用户会以为采集出了问题。

---

## 10. 真实数据（可拿来对数）

品牌 34 = 安踏 + 7 个竞品，10 条无提示提问，35 条 `answer_status=ok` 样本。

```text
n_valid = 35
安踏 m=21 → 60.0%    head 15 / middle 5 / tail 1
出场顺位分布：#1×6 · #2×5 · #3×5 · #4×4 · #5×1
SoV(安踏) = 21 / 137 = 15.3%
竞品区间 14.3%(鸿星尔克 5) ~ 62.9%(亚瑟士 22)
```

**这套数据的价值在于它不是平的：**

```text
国产 / 性价比 / 篮球类提问   →  安踏 5/5、4/4、3/3、3/3、3/3  （100%）
专业跑鞋 / 健身训练类提问     →  安踏 0/5、0/3                 （0%）
```

60% 是两极平均出来的。**只看总数会盖掉真问题** —— 所以 `group_by=prompt` 的下钻是必需能力，
不是锦上添花。

另有品牌 1 = 土巴兔，15 条样本，**本品 0 提及但 6 个竞品有命中**（3~9/15）——
零状态 UI 与「本品缺席、竞品在场」的天然用例。

> 快照日期 2026-08-06。重抓后会变，对数前先跑一次 `/v1/counts` 确认。

---

## 11. 联调清单

```bash
# 1. 登录（注意 -c 存 cookie）
curl -sc /tmp/c.txt -X POST https://geo.xg22.top/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"...","password":"..."}'

# 2. 我是谁
curl -sb /tmp/c.txt https://geo.xg22.top/v1/auth/me

# 3. 总览四个数
curl -sb /tmp/c.txt 'https://geo.xg22.top/v1/counts?brand_id=34'

# 4. 逐提问下钻（矩阵的数据源）
curl -sb /tmp/c.txt 'https://geo.xg22.top/v1/counts?brand_id=34&group_by=prompt'

# 5. 平台可用性
curl -sb /tmp/c.txt https://geo.xg22.top/v1/config/platforms

# 6. 某次运行的样本列表（轻量投影，响应里不该出现 full_text / raw_json）
curl -sb /tmp/c.txt 'https://geo.xg22.top/v1/responses/summary?run_id=27&limit=5'

# 7. 这次运行还有几条没回来（失败 job 不产出 response，只在这里看得见）
curl -sb /tmp/c.txt 'https://geo.xg22.top/v1/crawl-jobs?run_id=27&status=failed&limit=1'
```

前端首次接通的判据：**`/v1/counts?brand_id=34` 返回 `n_valid=35`、`m_mentioned=21`**。
