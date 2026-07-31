# L2 验收记录（计数层）

> 日期：2026-07-31  
> 状态：**代码已就绪（B6）；本步做正式验收 + DB 约束加固**  
> 原则：后端 **只出整数 counts**，不算比率；比率留给前端 L3

---

## 1. L2 在本项目的定义（已拍板）

| 项 | 约定 |
|----|------|
| 实现形态 | **2B**：`GET /v1/counts` 实时 group by（日表物化后置） |
| 分母 | 仅 `answer_status = ok` → `n_valid` |
| 分子 | `mentions` 表按品牌聚合的 **m_*** 整数 |
| 禁止 | API 返回提及率 / SoV / 综合分作为权威结果 |
| 配置 | `GET /v1/config/metrics` 下发枚举与默认权重说明 |

**不在本步做：** 前端 L3 看板、第二平台抓取、LLM 情感。

---

## 2. 相关表（数据库侧）

| 表 | L2 角色 |
|----|---------|
| `raw_responses` | 样本 + `answer_status`（分母） |
| `mentions` | 本品/竞品是否提到、类型、位置桶（分子） |
| `crawl_jobs` / `prompts` | 过滤 brand / prompt / platform |
| `competitor_links` | 决定 competitors[] 列表 |
| `metric_snapshots` | **MVP 不用**；表可空。权威不在此表（历史占位含 rate 列，禁止当 L2 真相源） |

### 本步 DB 加固

迁移 **`003_l2_mentions_unique`**（`apps/api/app/core/schema.py` + `deploy/init.sql`）：

- `UNIQUE (response_id, brand_id)` on `mentions` — 每条回答每个品牌最多一行标注  
- 辅助索引：`raw_responses(platform, created_at)`、`mentions(response_id)`

---

## 3. API 验收清单

| 检查 | 命令/方式 | 期望 |
|------|-----------|------|
| counts | `GET /v1/counts?brand_id=1&prompt_id=1&platform=deepseek` | 仅整数；含 denominator / brand / competitors |
| group_by | `...&group_by=day` | `series[]` 按 UTC 日分桶 |
| 口径配置 | `GET /v1/config/metrics` | answer_status / mention_types / position_buckets |
| 明细下钻 | `GET /v1/responses` | L0+L1，供核对 m 的来源 |
| SQL 对照 | `python -m app.scripts.verify_l2` | api 与 SQL 一致 → PASS |

### 2026-07-31 实测（VPS）

```text
brand_id=1, prompt_id=1, platform=deepseek
n_valid = 18
brand(1): m_mentioned=4, m_body=4, m_head=4, m_none=14
competitor(2): m_mentioned=0, m_none=18
competitor(3): m_mentioned=0, m_none=18
metric_snapshots = 0 行
```

SQL group by 与 API **一致**。

### 数据解读（质检，不是 API bug）

| 来源 | response id | 土巴兔命中 |
|------|-------------|------------|
| 假数据 worker | 1,3,4,5 | 是（4 次） |
| DeepSeek 真抓 | 6–18 | 当前样本 **均未**命中别名「土巴兔」等 |

因此「提及率」若前端算成 `4/18`，分子几乎全来自假数据。  
**L2 计数正确；业务上若要看真抓可见性，应过滤 fake 或清假数据 / 只统计 `raw_json.source=deepseek_web`。**  
（是否加 `source` 过滤参数 → 你拍板后再做，本步不擅自加。）

---

## 4. 代码位置

| 路径 | 说明 |
|------|------|
| `apps/api/app/api/counts.py` | 路由 |
| `apps/api/app/services/counts.py` | 聚合逻辑 |
| `apps/api/app/schemas/counts.py` | 响应模型 |
| `apps/api/app/scripts/verify_l2.py` | SQL↔API 验收脚本 |
| `docs/15-b6-counts-api.md` | B6 功能说明 |
| `docs/10-data-responsibility.md` | 分层职责 |

---

## 5. 开发规范（本步遵守）

1. **一步一事**：本步只验收/加固 L2，不开前端、不加平台。  
2. **Git**：中文/英文 commit 说明改动原因；不提交 `deepseek_storage.json`、截图大数据。  
3. **部署**：改 api 代码 → `git push vps main` → post-receive rebuild api；迁移靠 `ensure_schema`。  
4. **DB**：可重复执行的 `IF NOT EXISTS` 迁移；破坏性变更先验收再改。  
5. **口径**：counts API **永不**返回比率字段作为权威。  

---

## 6. L2 关闭条件（建议你确认）

- [x] `/v1/counts` 与 SQL 一致  
- [x] `/v1/config/metrics` 可用  
- [x] mentions 唯一约束迁移落地  
- [x] verify_l2 脚本可跑  
- [x] 文档记录假数据对分子的影响  
- [ ] （可选）是否清洗假数据或增加 source 过滤 — **待你拍板**

---

## 7. 本步之后的分叉（不擅自开做）

| 方向 | 说明 |
|------|------|
| A 前端 L3 | 吃 counts → 提及率/SoV/看板 |
| B 第二/三平台 | 扩 L0 抓取，L1/L2 复用 |
| C 数据治理 | 清 fake、加 source 过滤、扩 prompt/别名 |

你确认 L2 验收通过后，再选 A/B/C。
