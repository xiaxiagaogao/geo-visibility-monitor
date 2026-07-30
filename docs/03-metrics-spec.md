# 核心指标规格（MVP）

> 原则：可解释、可单测、权重可配置。  
> 算法思想对照 aeo-platform / ai-visibility，实现自研。

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
