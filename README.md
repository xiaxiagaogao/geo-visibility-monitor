# geo-demo

GEO 可见性监测 · 学习项目。**前后端分离**：后端抓数/标注/计数，前端展示（前端文档不在本仓堆叠）。

## 后端文档（只有这一份）

→ **[docs/BACKEND.md](docs/BACKEND.md)**（产品规格 + API + 鉴权 + VPS 运维）

历史材料（不必日常读）：`history/docs-archive/`

## 结构

```text
apps/api          API + worker
apps/web          前端占位（另线）
packages/metrics  指标纯逻辑
deploy/           compose / 发布
docs/BACKEND.md   后端唯一说明
```

## 后端开发流

本机改代码 → commit → `git push vps main` → VPS 跑服务（详见 BACKEND.md 运维部分）。
