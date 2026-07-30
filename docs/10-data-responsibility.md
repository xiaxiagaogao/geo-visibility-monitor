# 前后端数据职责边界（确认版）

> 日期：2026-07-30  
> 状态：**已确认**（用户采纳折中方案）

## 一句话

后端负责**抓得到、存得住、点得开**的数据（L0 + L1）；  
前端负责**看板怎么算、怎么画**（L2）；  
避免「前端每次扫全部全文」和「后端重型指标中台」两个极端。

## 分层

| 层 | 名称 | 责任方 | 内容示例 |
|----|------|--------|----------|
| **L0** | 原始采集 | 后端 | `full_text`、`citations`、`platform`、`prompt`、时间、`screenshot_path` |
| **L1** | 轻结构化 | 后端 | 是否命中别名、`mention_type`、首次位置 bucket/offset、可选 snippet |
| **L2** | 看板指标 | **前端** | 提及率、SoV、综合分、趋势、平台对比 |

## 对路线图

| 步骤 | 含义 |
|------|------|
| B3 | 任务 + 假 Worker → 写出 L0（假 full_text 即可） |
| B4 | L1 mention 落库（假数据或接 analyze） |
| B5 | DeepSeek 真抓 L0（+ 顺带 L1） |
| B6 | 查询 API 暴露 L0/L1 列表与详情 |
| B7 | 后端简易页看 L0/L1 质量 |
| 前端 | 基于 B6 做 L2 |

## 明确不做（MVP）

- 强制 `metric_snapshots` 流水线  
- 强制 `/v1/brands/{id}/metrics` 作为前端唯一数据源  
- 前端直连 PG / 前端 Playwright  

## 相关文档

- [01-mvp-scope](./01-mvp-scope.md)  
- [02-data-model](./02-data-model.md)  
- [03-metrics-spec](./03-metrics-spec.md)  
- [04-architecture](./04-architecture.md)  
