# MVP 范围（个人学习项目）

> 目标：本地 / 单机可跑的 GEO 投流分析闭环  
> 定位：**学习全栈**，非商用 SaaS

## 一句话

配置品牌与 Prompt → 抓取 AI 回答 → 计算提及等指标 → 仪表盘展示 + 原文钻取。

## In Scope（做）

| 模块 | 内容 |
|------|------|
| 品牌 | 主品牌 + 别名 + 竞品列表（单用户/单工作区即可） |
| Prompt | 手动录入、列表、标签（可选批量 CSV） |
| 抓取 | Playwright Worker；优先 DeepSeek，其次豆包；手动触发 + 简单定时 |
| 存储 | PostgreSQL：原始回答全文、结构化提及、指标快照；可选本地截图目录 |
| 指标 | 提及率、位置粗分、是否推荐、情感粗分、简化 SoV、趋势 |
| 前端 | 总览看板、Prompt 列表+原文、趋势图、竞品对比、设置页 |
| 部署 | docker-compose：web / api / worker / postgres / redis |

## Out of Scope（MVP 不做）

- 多租户 / 计费 / 完整 RBAC
- 账号池规模化、住宅代理池
- 告警中心、周报 PDF、Webhook
- 内容生成与多平台发布
- 海外全量模型（ChatGPT/Perplexity 可后补）
- Agent 自动优化建议

## 平台优先级

1. DeepSeek Web（POC 第一目标）
2. 豆包 Web
3. Kimi / 通义（有余力再加）

## 成功标准

- [ ] `docker compose up` 后本地可访问前端
- [ ] 可创建品牌与 3+ Prompt
- [ ] 至少 1 个平台能跑通抓取并入库
- [ ] 看板显示提及率与趋势
- [ ] 点击可看原始回答全文

## 建议迭代

| 迭代 | 产出 |
|------|------|
| M0 | 文档 + monorepo + metrics 单测 |
| M1 | API + DB + 品牌/Prompt CRUD |
| M2 | DeepSeek 抓取 POC + 入库 |
| M3 | 指标聚合 API + 基础看板 |
| M4 | 竞品对比 + 第二平台 |
