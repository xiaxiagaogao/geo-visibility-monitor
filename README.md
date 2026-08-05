# geo-demo — GEO 可见性监测（学习项目）

前后端分离：

| 侧 | 职责 | 文档 |
|----|------|------|
| **后端** | 抓取 AI 回答、L1 标注、L2 计数 API、运维质检 | **[docs/BACKEND.md](docs/BACKEND.md)** · **[docs/BACKEND-RUNBOOK.md](docs/BACKEND-RUNBOOK.md)** |
| **前端** | 展示、比率/图表、产品交互 | 前端工程自行维护（本仓 `apps/web` 可对接 API） |

定位：个人学习全栈；后端按可对接的数据产品设计，前端按展示产品设计。非商用 SaaS。

---

## 仓库结构

```text
apps/
  api/         FastAPI + crawl worker 入口
  web/         前端（另线构筑；后端不维护其产品文档）
  crawler/     抓取相关
packages/
  metrics/     可解释匹配/位置等纯逻辑
deploy/        docker-compose、Dockerfile、hook
docs/
  BACKEND.md           # 后端规格（活）
  BACKEND-RUNBOOK.md   # 后端运维（活）
  archive/             # 历史文档（只读）
```

---

## 后端快速入口

1. 读规格：[`docs/BACKEND.md`](docs/BACKEND.md)（定位、L0–L2、API、鉴权）  
2. 读运维：[`docs/BACKEND-RUNBOOK.md`](docs/BACKEND-RUNBOOK.md)（VPS、发布、抓取、排障）  
3. 本机改代码 → `git commit` → `git push vps main` → VPS 自动部署  
4. 公网 API：`http://<VPS>:8200`（需 `X-API-Key`；运维页 `/qa`）

指标库单测：

```bash
cd packages/metrics && pytest -q
cd apps/api && PYTHONPATH=. pytest tests/ -q
```

---

## 文档策略

- **日常只维护 2 篇后端活文档**（上表）。  
- 旧版 01–27 编号文、L3 草案、踩坑长文 → [`docs/archive/`](docs/archive/)，冲突时以活文档 + 代码为准。  
- 前端页面/IA 需求请写在前端仓库或 `apps/web` 侧，避免再次把 `docs/` 堆成杂物间。

---

## 根目录其它材料

- 早期头脑风暴 / 开源评估：仓库根目录 `# …md`（背景阅读，非现行规格）
