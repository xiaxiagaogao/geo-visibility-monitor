# D2 设计稿 · 用户体系与三角色权限

> 日期：2026-08-06
> 状态：**已定稿 · 实施中**
> 上游：[BACKEND.md](./BACKEND.md) §5 鉴权 · §11 已知债务
> 定稿后本文并入 BACKEND.md，不长期保留

---

## 0. 已拍板

| # | 决定 |
|---|------|
| 1 | 会话 = **服务端 session 存 Postgres + HttpOnly Cookie**（不用 JWT） |
| 2 | `/qa` 保留共享密钥，作为**超管后门** |
| 3 | 客户只看自己的品牌；运营可建品牌；**只有超管能管用户** |
| 4 | 首个超管**直接在数据库定义** |
| 5 | 客户角色**目前没有真实使用者，但完整实现并测试**（按有真人用来验收） |
| 6 | 客户**纯只读**；会话**固定 7 天**不滑动续期；建品牌时 workspace 必填 |

**评审后砍掉的五条**（避免为用不上的能力付复杂度）：

| 砍掉 | 理由 |
|------|------|
| `sessions.user_agent` / `ip` | 为不做的「登录设备管理」页准备的，存了没人看 |
| `last_seen_at` + 滑动续期 | 滑动续期等于每请求都可能写库；改固定 7 天，过期重登 |
| `revoked_at` 软删 | 没有审计页 —— 直接 DELETE 该行，效果相同、代码更短 |
| 独立的改密接口 | 并进 `PATCH /v1/users/{id}` |
| 登录失败限速 | 账号由超管手工建、密码可控，在线爆破风险远低于通用场景。见 §10 待办 |

**没砍的两条**（看着像讲究，其实性价比极高）：
`token_hash` 不存明文（多一行 sha256，换掉「备份泄露=会话失窃」）；
截图归属校验（§4.3，**不做则 §4.1/4.2 全部白做**）。

选 session 不选 JWT 的决定性理由：证据截图靠 `<img src>` 加载，**发不了自定义请求头**。
选 JWT 就得回头做 blob fetch 或签名 URL，把 D1 刚验证过的链路拆了重做。
其余理由（即时吊销、不引 Redis、XSS 防护）见对话记录。

---

## 1. 三条身份通道（并存，互不替代）

| 通道 | 载体 | 身份 | 用途 |
|------|------|------|------|
| **用户会话** | Cookie `geo_session` | `users` 行，带角色与 workspace | 前端唯一通道 |
| **共享密钥** | `X-API-Key` / `Bearer` | **等同超管**，无用户身份 | 脚本、运维、CI、`verify_l2` |
| **QA 后门** | Cookie `geo_qa_key` | **等同超管** | `/qa` 运维质检页 |

后两条是现状的延续，**不下放给前端**。前端只认第一条。

> 共享密钥保留是因为运维手册、部署自检、`docker exec ... curl` 全靠它。
> 把它降级成「机器凭证」而不是删掉，才不会为了纯洁性把运维路径砍断。

---

## 2. 表结构（迁移 `005_auth`）

```sql
CREATE TABLE users (
    id            SERIAL PRIMARY KEY,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('superadmin','operator','client')),
    -- 仅 client 有意义：他能看的品牌范围。operator/superadmin 看全部，此列为 NULL
    workspace_id  INT,
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login_at TIMESTAMPTZ
);

CREATE TABLE sessions (
    id          SERIAL PRIMARY KEY,
    user_id     INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    -- 存 token 的 SHA-256，不存明文：库被读走也换不出会话
    token_hash  TEXT NOT NULL UNIQUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at  TIMESTAMPTZ NOT NULL
);
CREATE INDEX idx_sessions_user ON sessions(user_id);
CREATE INDEX idx_sessions_expires ON sessions(expires_at);

登出与吊销 = **删行**，不留 `revoked_at`。过期清理靠 `expires_at` 索引定期删。
```

**两个刻意的选择：**

1. **`token_hash` 不存明文。** 会话 token 等价于密码，明文存库意味着一次备份泄露
   就能冒充任何在线用户。校验时对来件 token 做 SHA-256 再查。
   （这里不需要 bcrypt/argon2 —— token 是 32 字节高熵随机值，不可爆破，
   而每请求都要查一次，慢哈希会变成性能负担。密码才需要慢哈希。）
2. **`workspace_id` 只对 client 有意义。** 复用 `brands.workspace_id` 这个既有隔离键
   （BACKEND.md §3 记的「`Org → Workspace → Brand` 三层残留」），不新建关联表。
   一个客户往往不止一个品牌（安踏集团还有 FILA、迪桑特），workspace 天然装得下；
   多对多表则会带来「新增品牌忘了授权」的漏配风险。

### 密码哈希

新增依赖 **`argon2-cffi`**。不用 passlib —— 它在 Python 3.12 + bcrypt 4.x 上有已知
兼容问题，为一层封装引入不确定性不划算。argon2 是 OWASP 当前推荐。

---

## 3. 权限矩阵

| 能力 | 超管 | 运营 | 客户 |
|------|:---:|:---:|:---:|
| 看数据（counts / responses / 截图） | 全部 | 全部 | **仅本 workspace** |
| 品牌 / 别名 / 竞品 增改删 | ✓ | ✓ | ✗ |
| 提问词 增改删 | ✓ | ✓ | ✗ |
| 发起抓取、重试、重标注 | ✓ | ✓ | ✗ |
| 用户增删改、改角色、重置密码 | ✓ | ✗ | ✗ |
| `/qa` | ✓ | ✗ | ✗ |

**客户是纯只读。** 「客户能不能自助发起检测」你没提，我按不能处理 ——
抓取会消耗 DeepSeek 登录态且不可撤销，放给外部角色风险不对等。要开随时加。

---

## 4. 归属校验：三个必须堵的口子

「客户只看自己的品牌」不是在列表接口加个 `WHERE` 就完事。当前**所有**接口都不做归属校验，
逐个核过后有三类：

### 4.1 显式带 brand_id / prompt_id 的接口

`/v1/counts`、`/v1/prompts`、`/v1/responses`、`/v1/crawl-jobs`

前端传什么就查什么。客户改一个数字就能看别家数据。
**做法：** 统一的 `assert_brand_visible(user, brand_id)`；`prompt_id` 先反查其 brand。

### 4.2 列表接口的默认范围

不带参数时返回全部。**做法：** 客户身份下强制注入 workspace 过滤，不是可选参数。

### 4.3 【最隐蔽】截图按 basename 取，与品牌毫无关联

```
GET /v1/media/screenshots/deepseek_1785601999.png
```

这个路由只校验文件名安全性，**任何已认证用户都能拿到任何一张截图**。
文件名带时间戳，可枚举。客户借此能看到别家品牌的证据图。

**做法：** 先按 `raw_responses.screenshot_path = :basename` 反查 response
→ job → prompt → brand → workspace，再判可见性。查不到的一律 404
（不是 403 —— 403 会泄露「这张图存在」）。

> 这三条里只有 4.1 是「加个过滤」，4.2 是默认值问题，4.3 是**结构性缺口**。
> 前两条不做，客户看到别家数据；第三条不做，前两条做了也白做。

---

## 5. 接口

### 5.1 新增

| 方法 | 路径 | 谁能用 | 说明 |
|------|------|--------|------|
| POST | `/v1/auth/login` | 公开 | `{email, password}` → 下发 `geo_session` + `csrf_token` 两个 Cookie |
| POST | `/v1/auth/logout` | 已登录 | 撤销当前 session（写 `revoked_at`） |
| GET | `/v1/auth/me` | 已登录 | 返回 `{id, email, role, workspace_id}`，前端据此渲染菜单与按钮 |
| GET | `/v1/users` | 超管 | 用户列表 |
| POST | `/v1/users` | 超管 | 建用户 |
| PATCH | `/v1/users/{id}` | 超管 | 改角色 / 停用 / 换 workspace / **重置密码**（改密与停用都会删光该用户所有 session）|
| DELETE | `/v1/users/{id}` | 超管 | 删用户（级联删 session） |

> 登录失败限速**本轮不做**（见 §0 砍掉的五条）。账号由超管手工创建、
> 密码强度可控，在线爆破的实际风险远低于开放注册的通用场景。列入 §10 待办。

### 5.2 现有接口的鉴权变化

- 写接口：`X-API-Key`（机器）**或** 会话 Cookie + CSRF 头（用户）
- 读接口：三条通道均可，但会话身份要过归属校验
- `/health`、`/qa/login`、`/v1/auth/login` 保持公开

---

## 6. CSRF：现有防线会失效

**现在**靠「Cookie 只对 GET/HEAD/OPTIONS 有效」挡 CSRF。
**D2 之后写操作必须靠会话认证**，这条自动作废。

**替换为双提交 token：**

1. 登录时下发两个 Cookie：`geo_session`（HttpOnly）+ `csrf_token`（**非** HttpOnly）
2. 前端每次写操作把 `csrf_token` 的值放进 `X-CSRF-Token` 请求头
3. 服务端比对 Cookie 与请求头，不一致即 403

跨站攻击者读不到 `csrf_token`（同源策略），所以造不出合法请求头。

**顺带收紧 SameSite。** `geo.xg22.top` 与 `geo-api.xg22.top` 是**同一个 site**
（SameSite 判定用 eTLD+1 = `xg22.top`），所以 `Lax` 就够，不必用 `None`。
但 SameSite 是浏览器行为、`curl` 验不出来 ——
**等前端跑起来在真浏览器里验过再改**，不拿未验证的改动替换已验证的。

---

## 7. 中间件如何演进

现在是单一 `ApiKeyMiddleware`。改成**先认身份、再判权限**两段：

```text
① 认证中间件：解析三条通道 → request.state.principal
   （superadmin-machine / user(role, workspace_id) / anonymous）
② 路由依赖：require_role(...) / assert_brand_visible(...)
```

权限判断**不放在中间件**。中间件看不到路径参数与查询参数，做不了归属校验；
放依赖里才能拿到 `brand_id`，且哪个接口要什么权限一眼可查。

---

## 8. 首个超管

密码必须是 argon2 哈希，手写 SQL 没法生成。所以「在数据库定义」的可执行形式是：

```bash
docker exec -it geo-api python -m app.scripts.create_user \
  --email you@example.com --role superadmin
# 交互式输入密码，不走命令行参数（否则进 shell history 与进程列表）
```

脚本直接 INSERT 到 `users`，与手写 SQL 等价，只是把哈希算对。
**不做**「环境变量种子」——那会让密码常驻 `.env` 与容器环境。

---

## 9. 迁移与上线顺序

| 步 | 动作 | 风险 |
|---|------|------|
| 1 | 迁移 `005_auth` 建两张表 | 无（纯新增） |
| 2 | 建首个超管 | 无 |
| 3 | 上认证中间件，**三条通道并存** | 低：现有 `X-API-Key` 与 `/qa` 不受影响 |
| 4 | 上归属校验（§4 三条） | **中**：写错会让运营看不到数据。需按角色逐个接口验 |
| 5 | 上 CSRF 双提交 | 中：前端未适配前，用户会话的写操作会 403。**前端就绪后再开** |

3 之前**不会有任何行为变化**，现网可以随时停在第 2 步。

---

## 10. 明确不做

- 注册流程、邮箱验证、找回密码 —— 用户由超管创建
- OAuth / SSO
- 细粒度权限（按接口配权）—— 三个角色够用，别提前造框架
- 审计日志 —— 有价值但属另一件事
- 客户自助发起抓取（见 §3）
- **登录失败限速** —— 本轮砍掉，公网开放注册前必须补上

---

## 11. 已确认

| # | 问题 | 结论 |
|---|------|------|
| A | 客户是否纯只读 | **是**（抓取消耗 DeepSeek 登录态且不可撤销，不放给外部角色）|
| B | 会话有效期 | **7 天固定**，不滑动续期 |
| C | 运营建品牌时 `workspace_id` 谁定 | 建品牌时**必填** |
