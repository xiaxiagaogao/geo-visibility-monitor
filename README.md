# geo-demo

GEO 可见性监测（学习项目）。前后端分离：

- **后端：** 抓取 · 标注 · 计数 API → 说明见 **[docs/BACKEND.md](docs/BACKEND.md)**（唯一核心文档）
- **前端：** 展示 · 比率 · 交互 → 前端侧自建文档

```text
apps/api · apps/web · packages/metrics · deploy/
docs/BACKEND.md           # 现行唯一后端说明（历史 01–27 已全部提炼进来）
```

要翻旧文档：`git log --diff-filter=D -- history/`

开发：本机改代码 → `git push vps main` → VPS 运行（细节见 BACKEND.md §10）。
