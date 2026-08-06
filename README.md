# geo-demo

GEO 可见性监测（学习项目）。前后端分离：

- **后端：** 抓取 · 标注 · 计数 API → **[docs/BACKEND.md](docs/BACKEND.md)**（后端唯一核心文档）
- **对接：** 接口 · 鉴权 · 数据契约 → **[docs/API.md](docs/API.md)**（给前端看的）
- **前端：** 展示 · 比率 · 交互 → 前端侧自建文档

```text
apps/api · apps/web · packages/metrics · deploy/
docs/BACKEND.md           # 后端现行说明（历史 01–27 已全部提炼进来）
docs/API.md               # 前端对接契约（字段由 openapi 导出核对）
```

要翻旧文档：`git log --diff-filter=D -- history/`

开发：本机改代码 → `git push vps main` → VPS 运行（细节见 BACKEND.md §10）。
