# B4 — L1 规则标注

## 白名单（拍板）

| 字段 | 落点 |
|------|------|
| `answer_status` | `raw_responses`：`ok` / `empty` / `too_short`（分母） |
| 本品/竞品是否提到 | `mentions.mentioned` + `mention_type` |
| 首次位置 | `mentions.position_bucket`（body 命中时） |
| 证据片段 | `mentions.evidence_snippet` |
| 版本 | `raw_responses.annotator_version` = `l1-rules-v1` |

竞品范围 = 该 prompt 所属品牌的 `competitor_ids` + 本品。

## 触发

1. Fake worker 写完 L0 后自动 L1  
2. `POST /v1/responses/{id}/annotate`  
3. `POST /v1/responses/annotate/run?limit=50` 回填  

## 非目标

- LLM 情感（后置、后端）  
- L2 counts API（B6）  
- 真抓 DeepSeek（B5）  
