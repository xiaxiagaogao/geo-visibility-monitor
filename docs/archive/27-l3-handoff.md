# L3 前端交接（新会话从这里开始）

> 日期：2026-08-02
> 用途：**给一个全新会话的冷启动文档**。读完这一篇 + docs/23 + docs/26，
> 不需要回溯之前的对话就能开工 F0b。
> 上游：[24-code-review-fixes](./24-code-review-fixes.md) · [25-l3-kickoff](./25-l3-kickoff.md) · [26-monitoring-set-anta](./26-monitoring-set-anta.md)

---

## 1. 现在在哪一步

```text
后端 B1–B7 ✅ → 代码 review 修复 ✅ → 数据 D1/D2 ✅ → F0a 鉴权 ✅ → 【F0b 建前端工程】← 你在这
                                                                    → F1 → F2 → F3 → F4 → F5
```

| 状态 | 内容 |
|------|------|
| ✅ | 18 个 commit 的 review 修复（8 个 bug，含 2 个 VPS 实测才发现的 P1） |
| ✅ | 安踏监测集：8 品牌 + 10 条无提示 prompt + 35 条真实样本 |
| ✅ | 抓完即删会话闭环（35 次抓取后账号零残留） |
| ✅ | F0a：鉴权按 HTTP 方法切分，`GET` 可用 Cookie |
| ⬜ | **F0b：建 Next.js 工程** ← 下一步 |
| ⬜ | F1 API 客户端 + L3 纯函数 · F2 总览 · F3 明细/详情 · F4 任务 · F5 挂 VPS |

**自检基线**（改动后应保持）：

```bash
cd apps/api && PYTHONPATH=. pytest tests/ -q     # 78 passed, 7 skipped
cd packages/metrics && pytest -q                 # 16 passed
```

7 个 skipped 需要真实 Postgres，在 VPS 容器里跑：

```bash
docker exec -w /app/apps/api -e PYTHONPATH=. \
  -e GEO_TEST_DATABASE_URL="postgresql+psycopg://geo:geo@postgres:5432/geo" \
  geo-api python -m pytest tests/ -q
```

---

## 2. 环境（**本机不跑服务**）

本机没有 Docker，也不起服务 —— 只写代码 + `git push`，**运行与测试全在 VPS**（docs/08）。

```bash
# 部署：推 main 即触发 post-receive 自动 build + up
./scripts/push-vps.sh

# 上机
ssh -i /Users/xiagao/Desktop/pem/SG-DC1.pem -o IdentitiesOnly=yes root@96.9.213.230
```

| 项 | 值 |
|----|-----|
| API | `http://96.9.213.230:8200`（公网，需 API Key） |
| 容器 | `geo-api` / `geo-crawler` / `geo-postgres` |
| 部署目录 | `/opt/geo-demo`，compose 在 `deploy/` |
| 部署日志 | `/var/log/geo-demo-deploy.log` |

**同机还跑着 sillytavern(8100) 和 fund-dashboard(8090)，别碰。**

### API Key

存在 VPS 的 `deploy/.env`（chmod 600）。取：

```bash
ssh -i /Users/xiagao/Desktop/pem/SG-DC1.pem -o IdentitiesOnly=yes root@96.9.213.230 \
  "grep '^API_KEY=' /opt/geo-demo/deploy/.env"
```

> 别把 key 写进任何文件、日志或提交。

---

## 3. F0a 已完成 —— 这决定了前端怎么取数

**鉴权分界线是 HTTP 方法，不是路径**（`apps/api/app/core/security.py`）：

| 通道 | 适用 |
|------|------|
| 请求头 `X-API-Key` / `Authorization: Bearer` | 任何方法 |
| HttpOnly Cookie `geo_qa_key`（`path=/`） | **只对 GET / HEAD / OPTIONS** |

对前端的直接含义：

- **读数据（`GET /v1/*`）和证据截图靠 Cookie**，前端代码里**不需要也不应该**持有 API Key
- **写操作（创建抓取任务等）必须带请求头** —— 需要用户在界面上粘一次 key，或后续做真正的会话登录
- 登录入口现成：`POST /qa/login`（表单 `key=...`）→ 下发 Cookie → 之后同源 GET 全通

> 这条 CSRF 红线有测试守着（`test_cookie_never_works_for_write_methods` 逐方法验证），**不要为了方便把 Cookie 放开给写接口**。

---

## 4. 已拍板的决定（不用重新讨论）

| # | 决定 | 出处 |
|---|------|------|
| 1 | **Next.js + TypeScript**，配 `output: 'export'` 静态导出 | 用户拍板；docs/04 §5.3 |
| 2 | **同源**：前端构产物由 geo-api 托管，仍走 8200 | 用户拍板 |
| 3 | **深色监控风延续**，沿用 `/qa` 的色底并正式化成 token | 用户拍板 |
| 4 | 顶层 IA **以品牌/时间为主**，不学 g1geo 的任务为主 | 用户拍板 |
| 5 | 采纳 g1geo 的**下钻交互**（矩阵 → 点格子 → 模态） | 用户拍板 |
| 6 | `/v1/counts` **不加 category 参数** | 用户拍板 |
| 7 | 提问词**一律不含监测品牌名** | 用户拍板 |

**②+① 的推论：必须静态导出，没有 SSR / 服务端组件 / 中间件。** 对客户端取数的看板无影响，但写法上别用 `async` 服务端组件那套。

---

## 5. 设计产物

Claude Design 项目：

- [设计文档 v1（上下文 + token + 三个方向）](https://claude.ai/design/p/56a8ae49-0114-40c9-9e35-9b63372f0e14?file=index.html)
- [g1geo 拆解（借鉴 / 不抄 / 反着来）](https://claude.ai/design/p/56a8ae49-0114-40c9-9e35-9b63372f0e14?file=g1geo-teardown.html)
- [**v2 四屏全稿**（总览 / 矩阵 / 证据模态 / 任务）](https://claude.ai/design/p/56a8ae49-0114-40c9-9e35-9b63372f0e14?file=v2-screens.html) ← 以这份为准

> ⚠️ 浏览器沙箱挡住了预览域名，**v2 没有被渲染检查过**。几何与数值用脚本验过
> （条长与数值成比例、矩阵 80 格与真实数据逐一对上），但版式塌没塌需要人眼确认。

### 5.1 色彩 token（全部对 `#1a2332` 跑过 dataviz 验证器）

```css
/* 页面底 —— 沿用 /qa base.html */
--bg:#0f1419;  --card:#1a2332;  --card-2:#152031;
--text:#e7ecf3; --muted:#8b9bb4; --border:#2a3548;

/* 状态色：只做徽章，必须配文字。**绝不可当图表系列色** */
--ok:#22c55e;  --warn:#f59e0b;  --bad:#ef4444;

/* 图表系列色（dataviz 参考深色列，对本底色 6 项全 PASS，最差相邻 ΔE 8.4）*/
--s1:#3987e5; --s2:#d95926; --s3:#199e70; --s4:#c98500;
--s5:#d55181; --s6:#008300; --s7:#9085e9; --s8:#e66767;

/* emphasis 形态：主角 + 背景灰 */
--accent:#3987e5;  --dim:#3d4a61;

/* 矩阵格子顺序色阶（重取过档位，见下） */
--seq-1:#256abf; --seq-2:#3987e5; --seq-3:#6da7ec;
```

**两条硬约束**（都是跑验证器得出的，不是审美）：

1. **`--ok/--warn/--bad` 不能当图表系列色**：`#f59e0b ↔ #22c55e` 在红色盲下 ΔE 5.7，低于 6 的硬下限，且亮度超出深色带。作徽章没问题（始终配文字）。
2. **顺序色阶不能直接抄 dataviz 参考值**：最暗档 `#184f95` 对我们的 `#1a2332` 只有 1.95:1（参考值是对更暗的 `#1a1a19` 定的）。重取为 `#256abf → #6da7ec` 后全 PASS。

验证器用法：

```bash
node <dataviz-skill>/scripts/validate_palette.js "#hex,#hex" --mode dark --surface "#1a2332"
```

### 5.2 三条图表硬规则

1. **绝不用双轴。** `n_valid` 与提及率拆成两张小图。（docs/23 写的「双轴或双图」要划掉）
2. **竞品对比用 emphasis，不用 8 种颜色。** 本品 `--accent`，竞品统一 `--dim`。
3. **比率用线性 meter，不用环形 gauge**，并把 `m / n` 写在轨道下面。

### 5.3 一条产品级规范

**凡出现比率，必须同时显示 `m / n`。** 不允许孤零零的百分比 ——
这是 docs/10「分母唯一依据」在 UI 上的落地，也是这个产品可信度的来源。

---

## 6. 可用的数据（真实，不是 mock）

品牌 34 = 安踏，7 个竞品；10 条无提示 prompt；35 条 `answer_status=ok` 样本。

```bash
curl -H "X-API-Key: $KEY" 'http://96.9.213.230:8200/v1/counts?brand_id=34'
curl -H "X-API-Key: $KEY" 'http://96.9.213.230:8200/v1/counts?brand_id=34&group_by=prompt'
```

| 品牌 | 提及率 | m/n |
|------|--------|-----|
| 亚瑟士 | 62.9% | 22/35 |
| **安踏（本品）** | **60.0%** | **21/35** |
| 耐克 | 60.0% | 21/35 |
| 李宁 / 阿迪达斯 | 57.1% | 20/35 |
| 361度 | 48.6% | 17/35 |
| 特步 | 31.4% | 11/35 |
| 鸿星尔克 | 14.3% | 5/35 |

`SoV(安踏) = 21/137 = 15.3%` · 头部位置占比 `15/21 = 71.4%`

### 6.1 数据里最重要的一件事

**60% 是两极平均出来的，不是稳定表现：**

```
国产 / 性价比 / 篮球类提问   →  安踏 100%（5/5、4/4、3/3、3/3、3/3）
专业跑鞋 / 健身训练类提问     →  安踏 0%（0/5、0/3）
```

一个「60%」的大数字会把这个结论盖掉 —— **总览页的设计任务就是让这个数字当场自我解释**。
矩阵页（v2 的 2b）摆出来后，国产品牌与国际品牌的互补结构一眼可见。

### 6.2 另一套数据（零状态用例）

品牌 1 = 土巴兔，13 条有效样本，**本品提及率 0.0%**（真实结论，不是 bug ——
DeepSeek 回答装修类提问时确实不提它）。保留它正是为了验证零状态 UI 和多品牌切换。

---

## 7. 对 docs/21 / docs/23 的修正（以本文为准）

| 原文 | 改为 | 理由 |
|------|------|------|
| docs/21 §2 接口契约表 | 已过期 | 写在鉴权之前，见 §3 |
| docs/21 T1 建议 Vite | **Next.js** | 用户拍板 |
| docs/21 用 `category` 给 counts 加过滤参数 | **不做** | 砍掉有提示类后理由消失，`group_by=prompt` 已够 |
| docs/23 趋势「双轴或双图」 | **只能双图** | dataviz 硬规则 |
| docs/23 详情为 `/responses/:id` 独立页 | **矩阵内弹模态** + 保留独立页作永久链接（共用组件） | 保持上下文 |
| docs/23 证据用 `evidence_snippet` | 详情页改**全文内联高亮**；列表页仍用 snippet | 见 §8 |

---

## 8. 一个已解锁但还没用的能力

`match_brand` 返回的 `offset` **能正确索引原文**（docs/24 §1.2 修的 bug）。
当时修它是为了 `position_bucket` 算对，但它同时解锁了更好的证据展示：

> 详情页把 L0 全文渲染出来，**在命中位置内联高亮品牌名** ——
> 比一段掐头去尾的 40 字 snippet 可审计得多。

后端已具备条件（`mentions` 有 `position_bucket`，`match_brand` 有 offset 与 matched_term），
但**当前 API 不返回 offset**，前端要么后端补字段，要么前端自己按 `matched_term` 在
`full_text` 里找（注意大小写与别名）。**建议后端补 offset 字段**，别在前端重造匹配逻辑。

---

## 9. 踩过的坑（别重蹈）

| 坑 | 教训 |
|----|------|
| DeepSeek 删除接口 **HTTP 200 却没删** | 它把错误放 body（`code:40002`）。**验收要核对真实状态，不能信日志** |
| 直接套 dataviz 参考色板 | 参考值绑定它自己的底色，换底必须重跑验证器 |
| ORM 关系没配 `passive_deletes` | `DELETE` 有子行的品牌/Prompt 会 500。已修，改模型时别改回去 |
| SSE 流式拼接会丢首块 | L0 以 DOM 为真值优先。已修（`_pick_answer_text`） |
| 侧栏对话堆积会污染 DOM 抓取 | 抓完即删已上线；`deepseek_cleanup.py` 默认 dry-run，**账号里绝大多数是用户私人对话** |
| 本机没 Docker | 别试图本地起服务；测试进 VPS 容器 |

---

## 10. 工作方式约定（用户明确要求过）

1. **每一步单独 commit**，message 写清楚**根因 / 改动 / 验收**，不要一句话带过
2. **动生产库或跑批量抓取前先列步骤给用户过目**，不要直接执行
3. 提交前跑自检（§1 的两条命令）
4. VPS 上操作严格限定在 `geo-*`，其他项目不碰

---

## 11. F0b 具体要做什么

1. `apps/web` 建 Next.js + TS 工程，`next.config` 配 `output: 'export'`
2. 开发期取数：dev proxy 指向 `http://96.9.213.230:8200`（或 SSH 隧道到本地）
3. 定义 §5.1 的 token 为 CSS 变量 / Tailwind 主题
4. 构建产物挂进 geo-api 的静态路由 + 改 `deploy/Dockerfile.api`
5. 登录流程：复用 `POST /qa/login` 或做一个前端登录页打同一个接口

**验收：** `pnpm dev` 打开空壳，成功调到一次 `GET /v1/config/metrics`，
并且未登录时能正确跳转到登录页。

---

## 12. 明确不做（docs/22 Out of Scope + 本轮确认）

- 内容生成 / 文章发布 / 媒体分发（g1geo 有，我们不做）
- 营销大字 slogan 首屏
- PDF 周报 / 分享导出
- 情感指标（L1 后置，counts 里根本没有这个计数 —— 现在做就是编数据）
- 多租户 / 计费 / RBAC

---

## 13. 修订记录

| 日期 | 说明 |
|------|------|
| 2026-08-02 | 初版：F0b 冷启动交接 |
