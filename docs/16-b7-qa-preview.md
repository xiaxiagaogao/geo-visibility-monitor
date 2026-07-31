# B7 — 后端数据质量预览

## 入口

- 页面：`http://<host>:8200/qa`
- 根路径 `/` 重定向到 `/qa`

## 页面

| 路径 | 内容 |
|------|------|
| `/qa` | 总览：任务状态、answer_status、最近 job/response、brand1 counts 快照 |
| `/qa/jobs` | 任务列表，可按 status 筛选 |
| `/qa/responses` | L0/L1 列表 |
| `/qa/responses/{id}` | 全文、citations、mentions 明细 |

## 用途

在正式前端之前，用浏览器检查：

- 假/真抓是否写出 L0  
- L1 是否标注  
- 失败任务错误信息  
- counts 分子分母是否合理  

**不是** L3 正式看板。
