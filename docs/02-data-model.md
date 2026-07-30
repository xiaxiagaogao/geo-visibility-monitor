# 数据模型（MVP）

## 实体关系（简图）

```text
Brand ──< BrandAlias
Brand ──< CompetitorLink >── Brand(competitor)
Brand ──< Prompt
Prompt ──< CrawlJob
CrawlJob ──< RawResponse
RawResponse ──< Mention
RawResponse ──< Citation
Prompt × Platform × Window ── MetricSnapshot
```

单用户学习版可省略 User/Org；预留 `workspace_id` 字段默认 1。

## 表定义

### brands
| 字段 | 类型 | 说明 |
|------|------|------|
| id | serial PK | |
| workspace_id | int | 默认 1 |
| name | text | 主名称 |
| name_en | text null | |
| industry | text null | |
| created_at | timestamptz | |

### brand_aliases
| 字段 | 类型 | 说明 |
|------|------|------|
| id | serial PK | |
| brand_id | FK brands | |
| alias | text | 别名/简称/产品线 |

### competitor_links
| 字段 | 类型 | 说明 |
|------|------|------|
| id | serial PK | |
| brand_id | FK | 本品 |
| competitor_brand_id | FK | 竞品 |

### prompts
| 字段 | 类型 | 说明 |
|------|------|------|
| id | serial PK | |
| brand_id | FK | |
| text | text | 用户问题 |
| category | text null | 对比/推荐/百科… |
| tags | jsonb | `[]` |
| is_active | bool | |
| created_at | timestamptz | |

### crawl_jobs
| 字段 | 类型 | 说明 |
|------|------|------|
| id | serial PK | |
| prompt_id | FK | |
| platform | text | deepseek / doubao / … |
| status | text | pending/running/success/failed |
| sample_index | int | 多采样序号，默认 1 |
| error_message | text null | |
| started_at / finished_at | timestamptz null | |
| created_at | timestamptz | |

### raw_responses
| 字段 | 类型 | 说明 |
|------|------|------|
| id | serial PK | |
| job_id | FK crawl_jobs | |
| platform | text | |
| prompt_text | text | 冗余便于检索 |
| full_text | text | 完整回答 |
| html_path | text null | |
| screenshot_path | text null | |
| raw_json | jsonb null | 拦截到的原始结构 |
| latency_ms | int null | |
| created_at | timestamptz | |

### mentions
| 字段 | 类型 | 说明 |
|------|------|------|
| id | serial PK | |
| response_id | FK | |
| brand_id | FK | |
| mentioned | bool | |
| mention_type | text | body / citation_only / none |
| position_bucket | text null | head / middle / tail |
| position_rank | int null | 列表推荐名次 |
| is_recommended | bool | |
| sentiment | text null | positive/neutral/negative |
| sentiment_score | float null | -1..1 |
| evidence_snippet | text null | |

### citations
| 字段 | 类型 | 说明 |
|------|------|------|
| id | serial PK | |
| response_id | FK | |
| cite_index | int null | |
| url | text | |
| domain | text | |
| title | text null | |
| snippet | text null | |

### metric_snapshots
| 字段 | 类型 | 说明 |
|------|------|------|
| id | serial PK | |
| brand_id | FK | |
| prompt_id | FK null | null=品牌汇总 |
| platform | text | `all` 或具体平台 |
| window_start / window_end | timestamptz | |
| visibility_rate | float | |
| recommend_rate | float | |
| avg_position_score | float | |
| sentiment_net | float | |
| share_of_voice | float null | |
| sample_size | int | |
| extras | jsonb | 可扩展 |
| computed_at | timestamptz | |

## 索引建议

- `raw_responses(created_at)`
- `mentions(brand_id, response_id)`
- `crawl_jobs(status, platform)`
- `metric_snapshots(brand_id, platform, window_end)`
