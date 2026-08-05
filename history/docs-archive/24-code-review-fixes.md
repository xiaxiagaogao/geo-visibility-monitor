# 代码 Review 修复记录（L3 前）

> 日期：2026-08-01
> 状态：**已在 VPS 部署并验收通过**（api 64 passed / metrics 16 passed / verify_l2 PASS）
> 范围：全仓通读后的问题修复，**不含新功能**；做完即进 L3 前端

相关：[10-数据职责](./10-data-responsibility.md) · [03-指标规格](./03-metrics-spec.md) · [19-L2 验收](./19-l2-acceptance.md)

---

## 1. 修了什么

| 级别 | 问题 | 提交 |
|------|------|------|
| P0 | 公网 8200 无任何鉴权 | `feat(api): X-API-Key 鉴权` |
| P1 | `position_bucket` 取的不是首次提及 | `fix(metrics): position_bucket 取首次提及` |
| P1 | offset 与原文错位（strip + casefold） | 同上 |
| P1 | `_clean_answer_text` 改写 L0 原文 | `fix(crawl): L0 存原文` |
| P1 | job 僵死在 running 无法恢复 | `fix(api): 回收僵死任务` |
| P2 | counts 的 `to` 排除当天 | `fix(api): to 按当天末尾闭合` |
| P2 | 证据截图页 HTML 消毒可绕过 | `fix(crawl): 加 CSP` |
| P2 | 死代码与未使用 import | `chore(api): 清理` |
| P1 | **DELETE 品牌/Prompt 对有子行的记录 500** | `fix(api): 级联删除` |
| P1 | **L0 丢首块（流式拼接顶替）** | `fix(crawl): L0 优先取 DOM` |

> 后两条是**在 VPS 上实测才发现的**，本机静态阅读看不出来。详见 §1.5 / §1.6。

### 1.1 鉴权（P0）

`deploy/docker-compose.yml` 用 `"8200:8200"` 绑 0.0.0.0，全仓无任何认证。
公网上任何人都能 `DELETE /v1/brands/{id}`（级联删光抓取数据）、
`POST /v1/ingest/l0` 灌假数据污染 counts、触发抓取消耗 DeepSeek 登录态。

| 路径 | 认证方式 |
|------|----------|
| `/health` | 公开（部署探针） |
| `/health/config`、`/health/db` | 需 `X-API-Key` |
| `/v1/*`、`/docs` | **只认请求头**，`X-API-Key` 或 `Authorization: Bearer` |
| `/qa/*` | 额外认 HttpOnly Cookie，经 `POST /qa/login` 下发 |

**为什么写接口不认 Cookie：** 认了就等于开了 CSRF —— 第三方站点能诱导你的浏览器
带着 Cookie 发 `POST /v1/brands`。QA 页面全是 GET，只读，用 Cookie 才安全。

`API_KEY` 留空 = 完全不校验（本机开发），启动时打 WARNING。

### 1.2 首次提及（P1）

docs/03 §1.2 规定按「**首次**提及 offset」分桶，实现却按别名长度降序取第一个命中：

```
aliases = ["耐克", "耐克运动鞋"]
正文开头就出现「耐克」，文末才出现「耐克运动鞋」
→ 旧：offset=309/319 → tail(0.3)
→ 新：offset=0       → head(1.0)
```

配了「短名 + 长全称」的品牌，位置分会系统性偏低。

另外 `_norm()` 做了 `strip()`，返回的是归一化串下标，`annotate.py` 却拿它切原文 ——
正文带前导空白时 `evidence_snippet` 整段错位（`/v1/ingest/l0` 的 `full_text`
不做 strip，必中）。`casefold()` 改长度（ß→ss）是同一个根因。

改法：`_fold()` 长度守恒折叠，保证 offset 能直接索引原 body。

### 1.3 L0 原文（P1）

docs/10 定义 L0 = 原始回答，但抓取路径在写库前就改写正文且不留底。三条规则实测都伤正文：

| 规则 | 实测后果 |
|------|----------|
| `^6年` → `2026年` | 「6年内…」被写成「2026年内…」，且过 2026 必错 |
| 开头 `(FINISHEDSEARCH\|FINISHED\|SEARCH)+` 无边界 | 「SEARCH引擎优化…」被砍成「引擎优化…」 |
| 结尾 `(...)[\w一-鿿]*$` | `\w` 匹配中文，「…主营业务为家装SEARCH」被截断 |

现在 `full_text` 存原文；清洗结果进 `raw_json.cleaned_text`，且仅在确有改动时才写。
清洗只剥「开头且后接 串尾/空白/分隔符」的胶水 token，歧义时宁可留在 L0 不猜。

> **已入库的行原文已丢失，无法回填。** 此后新抓的才是真原文。

### 1.4 僵死任务（P1）

crawler 是 `restart: unless-stopped`，抓取中途被 OOM / Chromium 崩溃 / 重新部署打断时，
job 已 commit 成 `running` 却再没人管：`claim_pending_jobs` 只捞 `pending`，自己也不会超时。
更糟的是 `retry_job` 只放行 `failed`/`success`，`running` 直接 400 —— API 层完全无法自救。

现在 `run_once` 每轮先跑 `reclaim_stuck_jobs`：`started_at` 超过
`CRAWL_STUCK_JOB_SEC`（默认 600s）的收成 `failed`；`retry_job` 也放行 `running`。

收成 `failed` 而非直接回 `pending`：反复搞崩容器的任务不该自动无限重排。

### 1.5 级联删除（P1，VPS 实测发现）

在 VPS 上跑 `test_stuck_jobs` 时，teardown 报
`UPDATE prompts SET brand_id=NULL` → NotNullViolation。顺着查发现是生产代码的问题：

```text
DELETE /v1/brands/{id}   有 prompt 子行     -> 500 IntegrityError
DELETE /v1/prompts/{id}  有 crawl_job 子行  -> 500 IntegrityError
```

ORM 关系没配 `passive_deletes`，SQLAlchemy 删父行前会先把子表外键置 NULL，
而 `prompts.brand_id`、`crawl_jobs.prompt_id`、`raw_responses.job_id`、
`mentions.response_id`、`citations.response_id` 全是 NOT NULL ——
数据库层写好的 `ON DELETE CASCADE` 根本没机会执行。

全链路加 `cascade="all, delete"` + `passive_deletes=True`。

### 1.6 L0 丢首块（P1，VPS 真抓发现）

同一次真抓（job 37 / response 22）的两份文本：

```text
DOM     挑选一家靠谱的装修公司是件耗时又重要的事，…
stream  FINISHEDSEARCH一家靠谱的装修公司是件耗时又重要的事，…
```

SSE 拼接丢掉首块「挑选」，位置被控制 token `FINISHEDSEARCH` 顶替。
`_wait_for_answer` 原本在两者间「谁长选谁」，而带胶水的 stream 往往更长，
于是**每次都选中缺头的那份**。

历史样本的开头缺字全部由此而来，此前被旧的清洗规则掩盖成「看起来只是少了个词」：

| id | 入库正文开头 | 实际应为 |
|----|--------------|----------|
| 10 | 公司哪家好，其实没有标准答案… | 2026年装修**公司哪家好**… |
| 16 | 2026年的行业报告和市场调研… | 根据**2026年的行业报告**… |

首字直接决定 `position_bucket` 的 head/middle/tail，L0 不能将就。

改法：`_pick_answer_text` 以 DOM 为真值优先，stream 只在 DOM 明显更短
（仍在生成中）时兜底；侧栏噪声 DOM 一律不参与竞争。

**验证**：修复后重抓（job 38 / response 23），入库正文与 DOM 截图逐字一致，
无胶水前缀、无缺头。

> 存量 13 条历史样本的首块已永久丢失，重跑 L1 也补不回来 —— 只能靠重抓。

---

## 2. 上线步骤（按顺序）

```bash
# ① 推代码（post-receive 自动 build + up）
./scripts/push-vps.sh

# ② 设置 API_KEY —— 不做这步等于没修 P0
ssh -i "$GEO_VPS_PEM" root@96.9.213.230
cd /opt/geo-demo/deploy
python3 -c "import secrets; print('API_KEY=' + secrets.token_urlsafe(32))" >> .env
chmod 600 .env
docker compose up -d api
```

```bash
# ③ 验鉴权：无 key 应 401
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8200/v1/counts?brand_id=1
curl -s -o /dev/null -w '%{http_code}\n' \
  -H "X-API-Key: $API_KEY" 'http://127.0.0.1:8200/v1/counts?brand_id=1'
```

```bash
# ④ 重跑 L1（ANNOTATOR_VERSION 升到 l1-rules-v2，存量 position_bucket
#    与 evidence_snippet 必须重算才会修正）。多跑几次直到 processed=0
docker exec geo-api curl -s -X POST -H "X-API-Key: $API_KEY" \
  'http://127.0.0.1:8200/v1/responses/annotate/run?limit=500'
```

```bash
# ⑤ L2 复验
docker exec geo-api python -m app.scripts.verify_l2 --brand-id 1 --platform deepseek
```

```bash
# ⑥ 僵死回收的集成测试（需真库，本机没 Docker 跑不了）
docker exec -e GEO_TEST_DATABASE_URL="$DATABASE_URL" geo-api \
  python -m pytest tests/test_stuck_jobs.py -q
```

**验收标准**

- 无 key 访问 `/v1/*` 返回 401，带 key 返回 200
- `/qa` 在浏览器里跳转到 `/qa/login`，输入 key 后正常
- `annotate/run` 反复跑到 `processed=0`
- `verify_l2` PASS
- `docker logs geo-api` 无 `API_KEY 未设置` 警告

---

## 3. 测试

本机（无 Postgres，需真库的用例自动跳过）：

```bash
cd packages/metrics && pytest -q               # 16 passed
cd apps/api && PYTHONPATH=. pytest tests/ -q   # 57 passed, 7 skipped
```

VPS 容器内（真库，全部跑）：

```bash
docker exec geo-api pip install -q pytest httpx
docker exec -w /app/apps/api -e PYTHONPATH=. \
  -e GEO_TEST_DATABASE_URL="postgresql+psycopg://geo:geo@postgres:5432/geo" \
  geo-api python -m pytest tests/ -q          # 64 passed
docker exec -w /app/packages/metrics geo-api python -m pytest -q   # 16 passed
```

> `pytest` 不在生产镜像里（`pip install -e .` 不装 dev extras），每次重建后要重装。

### 2026-08-01 VPS 验收结果

| 项 | 结果 |
|----|------|
| 公网无 key 访问 `/v1/*` | 401 ✓（`/health` 仍 200） |
| 带 `X-API-Key` / `Bearer` | 200 ✓ |
| `/qa` 浏览器直访 | 302 → `/qa/login` ✓ |
| 登录后 Cookie（HttpOnly, Path=/qa） | ✓ |
| **同一 Cookie 打写接口** | **401 ✓**（CSRF 防线成立） |
| apps/api 测试 | 64 passed |
| metrics 测试 | 16 passed |
| `verify_l2` | PASS |
| L1 重跑 v1→v2 | 13 条，`answer_status` 与基线一致 |
| 真抓验证首块 | job 38 与 DOM 逐字一致 ✓ |

---

## 4. 没做 / 留给后面

| 项 | 说明 |
|----|------|
| `is_recommended` 恒 False | 符合 docs/10 的 L1 白名单（推荐度不在第一期）。但 `/v1/counts` 没有 `m_recommended`，**L3 算不出推荐率** —— 若前端要这个指标，需先扩 L1 白名单 |
| `/v1/counts` 全量加载 | 现在把所有 `RawResponse`（含 `full_text` 全文）拉进 Python 再累加，docs/19 说的却是「实时 group by」。样本量上千后要改成 SQL 聚合 |
| `apps/crawler/` 死代码 | README 自称「已并入 apps/api」，整目录无人引用，待确认后删 |
| `ensure_schema` 按 `;` 裸切 SQL | 当前迁移能跑，加函数/触发器会碎 |
| `verify_l2.py` 误报 | 改过 `competitor_links` 后，残留的旧 mention 行会让 SQL 侧多出品牌分组，比对报 FAIL |
| 存量 L0 原文 | 已被旧清洗改写 + 丢首块，无法回填；要干净数据只能重抓 |
| **本品/竞品 0 提及** | 11 条有效回答里 土巴兔/齐家网/住小帮 **一次都没出现**（SQL 直查确认，`mention_type=none` 是对的）。DeepSeek 答的是 匠云居装饰、品筑时代装饰、龙发装饰 等。L3 看板照现状会全是 0 —— 需要先扩别名库或调整 prompt，否则「监测台」没东西可看 |
| response 22 | 修复前抓的那条，正文带 `FINISHEDSEARCH` 前缀且缺首块，可按需删除 |

---

## 5. 修订记录

| 日期 | 说明 |
|------|------|
| 2026-08-01 | 初版：P0 鉴权 + 4 个 P1 + 3 个 P2 |
| 2026-08-01 | VPS 部署验收；实测新增 2 个 P1（级联删除、L0 丢首块）并修复 |
