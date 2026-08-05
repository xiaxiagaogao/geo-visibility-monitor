# B6 — 明细补充 + L2 Counts API

## 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/v1/counts` | **只返回整数计数**，不算比率 |
| GET | `/v1/config/metrics` | 口径配置（分母定义、权重默认值等） |
| GET | `/v1/responses` | L0+L1 明细（B4 已有） |

### `/v1/counts` 参数

| 参数 | 说明 |
|------|------|
| `brand_id` | 必填，监测主品牌 |
| `platform` | 可选 |
| `prompt_id` | 可选 |
| `from` / `to` | ISO 时间 |
| `group_by` | `none` \| `day` \| `platform` \| `prompt` |

### 返回（摘录）

- `denominator.n_valid`：有效样本数（`answer_status=ok`）
- `brand.m_mentioned` / `m_body` / `m_head`…
- `competitors[]`：各竞品同样计数字段
- `series[]`：按 `group_by` 分桶的计数

**前端 L3：** `提及率 = m_mentioned / n_valid`（仅当 n_valid>0）

## DeepSeek 登录何时做？

见下文与 `docs/14-b5-deepseek.md`：**在打开 `CRAWL_MODE=real` 之前**准备登录态；日常跑任务时 worker 自动用已保存的 state，不必每次人手点登录。

## 验收

正式验收与 DB 加固见 [19-l2-acceptance.md](./19-l2-acceptance.md)。
