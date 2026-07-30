# geo-demo — GEO 投流分析系统（个人学习）

从零全栈学习项目：后端抓取 + 指标派生 + 前端仪表盘。

## 文档

- [头脑风暴 v1](./%23%20GEO投流分析系统%20全栈构建头脑风暴（第一版）.md)
- [开源项目评估](./%23%20开源项目评估（可用于GEO系统）.md)
- [MVP 范围](./docs/01-mvp-scope.md)
- [数据模型](./docs/02-data-model.md)
- [指标规格](./docs/03-metrics-spec.md)
- [前后端架构（详细）](./docs/04-architecture.md)
- [Git 工作流](./docs/05-git-workflow.md)
- [B1 数据库](./docs/06-b1-database.md)
- [Docker 安装验收](./docs/07-docker-setup.md)（本机可选）
- [VPS 部署](./docs/08-vps-deploy.md)（**当前运行环境**）
- [B2 配置域 API](./docs/09-b2-config-api.md)
- [数据职责 L0–L3 拍板](./docs/10-data-responsibility.md)
- [指标分工 v0.1](./docs/11-metrics-fe-be-split.md)
- [B3 抓取任务](./docs/12-b3-crawl-jobs.md)
- [B4 L1 标注](./docs/13-b4-l1-annotate.md)
- [B5 DeepSeek](./docs/14-b5-deepseek.md)
- [B6 Counts API](./docs/15-b6-counts-api.md)

## 仓库结构

```text
apps/
  api/        FastAPI 业务 API
  web/        Next.js 前端（后续）
  crawler/    Playwright 抓取 Worker
packages/
  metrics/    可解释指标库（纯逻辑 + 单测）
deploy/       docker-compose 等
docs/         设计文档
```

## 快速开始（指标库）

```bash
cd packages/metrics
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
```

## 状态

- [x] 产品头脑风暴 / 开源评估
- [x] MVP 文档 + monorepo 骨架
- [x] metrics 包 + 单测
- [x] Git 规范
- [x] B1 数据库落地（schema + 连接 + 校验脚本）
- [x] B2 配置域 API（品牌/Prompt CRUD）
- [x] B3 任务 + 假 Worker（L0）
- [x] B4 L1 规则标注
- [x] B5 DeepSeek Web Provider（fake/real）
- [x] B6 counts API
- [ ] B7 后端数据可视化（抓取质量）
- [ ] 正式前端（B6/B7 之后）

## 路线（已确认）

- **运行环境：VPS**（本机只写代码 + git push，不做本地 Docker 验收）
- **数据职责（已拍板）**：L0/L1/L2 后端（L2=counts）；**L3 比率前端**（见 docs/10、docs/11）

后端 B1→…→B6 → **B7 后端数据预览** → 前端。  
实现中按需对照开源，减少重复劳动。
