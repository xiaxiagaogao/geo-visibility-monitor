# MVP 范围（个人学习项目）

> 目标：本地 / 单机可跑的 GEO 投流分析闭环  
> 定位：**学习全栈**，非商用 SaaS

## 一句话

配置品牌与 Prompt → 抓取 L0 → 标注 L1 → 计数 L2(API) → 前端 L3 比率与看板 + 原文钻取。

## In Scope（做）

| 模块 | 内容 |
|------|------|
| 品牌 | 主品牌 + 别名 + 竞品列表（单用户/单工作区即可） |
| Prompt | 手动录入、列表、标签（可选批量 CSV） |
| 抓取 | Playwright Worker；优先 DeepSeek，其次豆包；手动触发 + 简单定时 |
| 存储 | L0 raw + L1 标注（mentions 等）；L2 以 counts API 为主 |
| 指标 | L2 后端只出**计数**；L3 前端出**比率/综合分/趋势** |
| 前端 | 看板 L3 + 原文钻取；不跑 Playwright、不做 LLM 情感 |
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
| M3 | 明细 API + counts API + 前端 L3 基础看板 |
| M4 | 竞品对比 + 第二平台 |


## 前后端数据职责（2026-07-30 拍板 · 以 docs/10 为准）

| 层 | 谁 | MVP |
|----|----|-----|
| L0 Raw | 后端 | 原文/引用/平台/prompt/时间/截图 |
| L1 标注 | 后端 | answer_status、本品/竞品提及、mention_type、首次位置 |
| L2 计数 | 后端 | **counts API**（日表物化后置） |
| L3 比率 | 前端 | 提及率/SoV/综合分/趋势；只吃 counts |

- 首抓平台：**DeepSeek Web**  
- LLM 情感：**不放前端**；后置后端 L1  
- 详见 [10-data-responsibility](./10-data-responsibility.md)、[11-metrics-fe-be-split](./11-metrics-fe-be-split.md)
