# GEO Demo · 前端对接契约

> **给前端看的唯一接口文档。** 字段清单由 `app.openapi()` 导出核对，不是凭记忆写的。
> 后端职责与内部约定见 [BACKEND.md](./BACKEND.md)；两者冲突时**以代码为准**，并回来改文档。
> 在线 schema：`GET /openapi.json` · 交互式：`GET /docs`

---

## 1. 接入信息

| 项 | 值 |
|----|-----|
| Base URL | `https://geo-api.xg22.top`（Cloudflare → Caddy → `geo-api:8200`） |
| 前端 Origin | `https://geo.xg22.top`（已在 CORS 白名单） |
| 跨域 | 已开 CORS 且 `allow_credentials=true`；**fetch 必须带 `credentials: 'include'`** |
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

**token 从响应体拿，不要去读 Cookie。** 跨域部署下你读不到 ——
`geo_csrf` 是 `geo-api.xg22.top` 的 host-only Cookie，而你在 `geo.xg22.top`。
`login` 与 `me` 的响应体里都有 `csrf_token`，存内存即可（**别进 localStorage**）。

```ts
// 登录时拿到；刷新页面后从 GET /v1/auth/me 重新拿
const { csrf_token } = await login(email, password)

fetch(url, { method: 'POST', credentials: 'include',
             headers: { 'X-CSRF-Token': csrf_token, 'Content-Type': 'application/json' } })
```

> ⚠️ **开发期走代理会掩盖这个问题。** next rewrites 下 Cookie 落在 localhost，
> `document.cookie` 读得到，老写法验证会通过 —— 然后一上生产全线 403。

> 后端开关 `CSRF_PROTECTION_ENABLED` 现在是 `false`，**不带这个头也能写**。
> 但请从第一天就带上 —— 等前端在真浏览器里验通了，后端会打开开关；
> 到那时没带头的写操作会全部 403。

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
前端不必也不应该自己加过滤。唯一例外：`/v1/crawl-jobs` 对客户**必须传 `prompt_id`**，
否则 400（任务列表本身会泄露别家在监测什么）。

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
| `group_by` | | `none`(默认) \| `day` \| `platform` \| `prompt` |
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
                   "m_head": 15, "m_middle": 5, "m_tail": 1 },
  "competitors": [ /* 同结构 × N */ ],
  "series":      [ /* group_by ≠ none 时：{ key, denominator, brand, competitors } */ ]
}
```

**全是整数，永远不返回比率。**

### 4.1 前端自己算

```ts
提及率      = m_mentioned / n_valid
头部占比    = m_head / m_mentioned
SoV         = m_本品 / (m_本品 + Σ m_竞品)
分母为 0 → 显示「—」，不要显示 0%
```

### 4.2 四个必须记住的坑

1. **任意时间窗一律 `Σm / Σn`，绝不能把日比率求平均。** 分母不等时两者不相等，
   平均出来的数字没有任何口径。这是「后端只给整数」的根本理由。
2. **`group_by=prompt` 的 `series[].key` 是 prompt_id 字符串，不是提问文案。**
   行标题要自己去 `/v1/prompts` 关联。`group_by=day` 的 key 是 **UTC 日期**。
3. **`competitors[]` 按 `brand_id` 关联，不许按数组下标** —— 顺序不保证。
4. **凡显示比率，必须同时显示 `m / n`。** 孤零零的百分比在这个产品里没有可信度。

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

参数：`platform` · `prompt_id` · `brand_id` · `answer_status` · `limit`(≤200) · **`offset`**

```jsonc
{ "items": [RawResponseOut], "total": 50 }   // total 是过滤后全量，不受分页影响
```

`RawResponseOut`：`id` · `job_id` · `platform` · `prompt_text` · **`full_text`** ·
`screenshot_path?` · `raw_json?` · `latency_ms?` · `answer_status?` ·
`annotator_version?` · `created_at` · `citations[]` · `mentions[]`

> ⚠️ **每一行都带完整 `full_text`。** 矩阵渲染时别一次拉全量，
> 只在点开某个格子时按 `prompt_id` 拉。

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

```
full_text.slice(first_offset, first_offset + matched_term.length) === matched_term
```

`first_offset` 非空时**必然成立**（后端在全库 179 条命中上验过 179/179）。
前端可以拿它 assert 一下，错位会立刻暴露。

**禁止**自己拿 `matched_term` 去 `full_text` 里 `indexOf` —— 会和 L1 标注口径分叉
（大小写折叠、别名优先级规则都在后端）。

**`position_rank` 的口径**：正文命中的品牌按 `first_offset` 升序排名，
只在**被监测品牌集合内**排。回答里先提到未监测的品牌时，我方 `rank=1` 仍是 1 ——
含义是「我们关心的品牌里它最先出现」，**不是「AI 首推我们」**。
`citation_only` 是 `null`（正文没出现），不是排最后。

### `GET /v1/media/screenshots/{basename}`

`RawResponseOut.screenshot_path` **已经是 basename**，直接拼即可：

```html
<img src="https://geo-api.xg22.top/v1/media/screenshots/deepseek_1785601999.png">
```

跨站 `<img>` 会自动带上会话 Cookie（`SameSite=None; Secure`）。
响应带 `Cache-Control: private, no-store`，**不要在前端缓存它**。

---

## 8. 任务

### `GET /v1/crawl-jobs`

参数：`status` · `platform` · `prompt_id` · `limit`(≤200) · **`offset`**

`CrawlJobOut`：`id` · `prompt_id` · `platform` · `status` ·
**`sample_index`**（同一 prompt 的第几次采样）· `error_message?` ·
`started_at?` · `finished_at?` · `created_at` · **`response_id?`**（可直接下钻）

`status`：`pending` → `running` → `success` / `failed`

### `POST /v1/crawl-jobs`（仅超管/运营）

```jsonc
{ "prompt_id": 23, "platform": "deepseek", "samples": 3 }  // → 返回 3 个 job
```

**未接入的平台会 400 并列出当前可用平台** —— 不会先建成功再默默失败。

### `POST /v1/crawl-jobs/{id}/retry`

`failed` / `success` / `running` 都可重排（`running` 是为了救僵死任务）。

---

## 8.5 检测任务与运行

**任务（Task）= 命名的监测定义**（一个主品牌 + 平台 + 采样数），可反复执行。
**运行（Run）= 一次执行**。`crawl_jobs` 挂在 run 下面。

| 方法 | 路径 | 备注 |
|------|------|------|
| GET / POST | `/v1/tasks` | 列表按 workspace 自动收敛；建任务仅超管/运营 |
| GET / PATCH | `/v1/tasks/{id}` | PATCH **不含 `brand_id`** —— 任务过不了户 |
| GET | `/v1/tasks/{id}/runs` | 该任务的执行历史 |
| POST | `/v1/tasks/{id}/runs` | 发起一次运行，仅超管/运营 |
| GET | `/v1/runs/latest` | **我能看到的最新一次运行**。客户首页分流用；一次都没有时 404 |
| GET | `/v1/runs/{id}` | 带口径快照 |

`TaskOut`：`id` · `brand_id` · `name` · `platforms[]` · `samples` · `is_active` ·
`created_at` · `latest_run_id?` · `latest_run_at?` · `latest_run_status?`

`RunOut`：`id` · `task_id` · `platforms[]` · `note?` · `created_at` · **`status`** · `n_jobs`

`RunDetailOut` = `RunOut` + **`prompts[]`**（`prompt_id` + `prompt_text`）
+ **`competitors[]`**（`competitor_brand_id` + `brand_name`）

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
curl -sc /tmp/c.txt -X POST https://geo-api.xg22.top/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"...","password":"..."}'

# 2. 我是谁
curl -sb /tmp/c.txt https://geo-api.xg22.top/v1/auth/me

# 3. 总览四个数
curl -sb /tmp/c.txt 'https://geo-api.xg22.top/v1/counts?brand_id=34'

# 4. 逐提问下钻（矩阵的数据源）
curl -sb /tmp/c.txt 'https://geo-api.xg22.top/v1/counts?brand_id=34&group_by=prompt'

# 5. 平台可用性
curl -sb /tmp/c.txt https://geo-api.xg22.top/v1/config/platforms
```

前端首次接通的判据：**`/v1/counts?brand_id=34` 返回 `n_valid=35`、`m_mentioned=21`**。
