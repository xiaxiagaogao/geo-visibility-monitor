# 核心指标规格（MVP）

> 原则：可解释、可单测、权重可配置。  
> 算法思想对照 aeo-platform / ai-visibility，实现自研。

## 0. 职责边界（2026-07-30 修订）

| 层级 | 谁算 | 落点 |
|------|------|------|
| **L0 原始数据** | 后端采集 | `raw_responses.full_text`、`citations`、platform、prompt、时间、截图路径 |
| **L1 轻结构化** | 后端（抓取后或同步试算） | 是否命中本品/竞品别名、首次出现 offset/bucket；可选 evidence 片段 — **主要为 B7 质检与降低前端全量扫文压力** |
| **L2 看板指标** | **前端派生**（主） | 提及率、推荐率、SoV、综合分、趋势序列；后端 **不强制** `metric_snapshots` 写入与 `/metrics` 聚合 API |

### 对实施步骤的影响

| 原步骤 | 修订 |
|--------|------|
| B4 metrics 接入落库 | **降级为 L1**：写轻结构化 mention（命中/位置），**不做**看板级 snapshot 强依赖 |
| B6 查询域 API | **以原文 + L1 列表/详情为主**；聚合 metrics 接口可选，MVP 可砍 |
| `packages/metrics` | 仍可供后端 L1、API 试算、或前端对照算法；**不是**前端必须调用的聚合服务 |

### 为何不全丢给前端？

纯前端对每条 `full_text` 做别名扫描，在数据量上来后会卡。L1 由后端在入库时算一次，前端看板只做**聚合与绘图**，压力更小。

## 1. 单次回答级（per RawResponse × Brand）

### 1.1 mentioned
- **定义**：回答正文或引用中命中品牌名/任一别名（大小写不敏感；中文直接子串）。
- **mention_type**：
  - `body`：正文命中
  - `citation_only`：仅引用源标题/snippet 命中
  - `none`：未命中
- **presence hit**（用于提及率分子）：`body` 或 `citation_only` 都算 hit（可配置是否只算 body）。

### 1.2 position_bucket
将全文按字符三等分：
- `head`：首次提及 offset ∈ [0, L/3)
- `middle`：∈ [L/3, 2L/3)
- `tail`：∈ [2L/3, L)
- 未提及：null

### 1.3 position_score
| bucket | score |
|--------|-------|
| head | 1.0 |
| middle | 0.6 |
| tail | 0.3 |
| none | 0.0 |

### 1.4 is_recommended
启发式规则（可后续换模型）：
- 出现「推荐」「首选」「建议选择」等且窗口内有品牌名；或
- `position_rank == 1`

### 1.5 sentiment
MVP：关键词粗分
- 正面词 / 负面词命中计数 → positive / negative / neutral
- `sentiment_score`：pos 记 +1，neg 记 -1，归一到约 [-1, 1]

## 2. 聚合级（窗口内）

窗口：默认近 7 天；维度：`brand_id` × `platform` × 可选 `prompt_id`。

设有效样本 N = 成功回答数（失败 job 不计入分母）。

| 指标 | 公式 |
|------|------|
| **visibility_rate** | hits / N |
| **recommend_rate** | recommended_count / N |
| **avg_position_score** | sum(position_score) / N |
| **sentiment_net** | mean(sentiment_score) |
| **share_of_voice** | brand_hits / (brand_hits + sum(competitor_hits)) |

### 综合可见性分（0–100，可选）

对照常见权重（可配置）：

```
score = 100 * (
  0.40 * visibility_rate +
  0.30 * avg_position_score +
  0.30 * ((sentiment_net + 1) / 2)
)
```

## 3. 多采样（Phase 1.5）

同一 prompt × platform 跑 K 次：
- 每次得到 mention ∈ {yes, src, no}
- presence_rate = count(yes|src) / count(measured)  （error 不进分母）
- 代表值：众数，并列时 yes > src > no

## 4. 配置默认值

```yaml
presence_include_citation_only: true
position_scores: {head: 1.0, middle: 0.6, tail: 0.3}
visibility_weights: {mention: 0.4, position: 0.3, sentiment: 0.3}
```
