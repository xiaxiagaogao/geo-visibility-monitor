# GEO Demo · 后端运维手册

> 配套规格：[BACKEND.md](./BACKEND.md)  
> 环境：**本机写代码 + git push；运行在 VPS**（本机可不跑 Docker）

---

## 1. 环境一览

| 项 | 值 |
|----|-----|
| VPS | `96.9.213.230` |
| SSH 示例 | `ssh -i ~/Desktop/pem/SG-DC1.pem -o IdentitiesOnly=yes root@96.9.213.230` |
| 裸仓库 | `/opt/geo-demo.git` |
| 工作树 | `/opt/geo-demo` |
| Compose | `/opt/geo-demo/deploy` |
| 部署日志 | `/var/log/geo-demo-deploy.log` |
| API | `http://96.9.213.230:8200` |
| 容器 | `geo-api` · `geo-crawler` · `geo-postgres` |

**同机勿碰：** sillytavern `:8100`、fund-dashboard `:8090`、系统 nginx 80/443。

| 本服务端口 | 绑定 |
|------------|------|
| API | `0.0.0.0:8200`（公网，需 API Key） |
| Postgres | `127.0.0.1:5433` → 容器 5432 |
| 截图 | 容器内 `/data/screenshots`（volume） |

私钥、`deploy/.env`、`deepseek_storage.json`：**禁止 commit**。

---

## 2. 日常发布

```bash
# 本机仓库
cd /Users/xiagao/Desktop/geo-demo
git status
git add <files>
git commit -m "type(scope): 说明"
# 推荐：
export GIT_SSH_COMMAND='ssh -i /Users/xiagao/Desktop/pem/SG-DC1.pem -o IdentitiesOnly=yes'
git push vps main
# 或 ./scripts/push-vps.sh（若存在）
```

`post-receive` 会 checkout 工作树并 `docker compose build/up`（含 crawler 若已存在容器）。  
关注：`tail -f /var/log/geo-demo-deploy.log`。

**改 crawler/截图逻辑后确认镜像已重建：**

```bash
docker exec geo-crawler grep -n "关键符号" /app/apps/api/app/providers/deepseek_web.py | head
```

**DeepSeek 登录态（volume 丢失时）：**

```bash
# 本机导出 storage_state 后
docker cp deploy/deepseek_storage.json geo-crawler:/data/deepseek_storage.json
# 确保 compose 中 DEEPSEEK_STORAGE_STATE=/data/deepseek_storage.json
```

---

## 3. 鉴权与调试请求

```bash
# 读取 key（勿回显到聊天/文档）
ssh ... "grep '^API_KEY=' /opt/geo-demo/deploy/.env"

export KEY='...'   # 本地终端临时
curl -s -H "X-API-Key: $KEY" http://96.9.213.230:8200/health
curl -s -H "X-API-Key: $KEY" "http://96.9.213.230:8200/v1/counts?brand_id=34" | jq .
```

- **写接口**必须 Header Key  
- **QA 读页面：** 浏览器打开 `/qa/login` 提交 key → Cookie 后浏览 `/qa/responses`  
- Cookie **不能**代替 POST 建任务  

---

## 4. 常用业务操作

### 4.1 健康

```bash
curl -s http://127.0.0.1:8200/health          # VPS 上
curl -s -H "X-API-Key: $KEY" http://127.0.0.1:8200/health/db
docker ps --filter name=geo
```

### 4.2 触发抓取

```bash
curl -s -X POST http://127.0.0.1:8200/v1/crawl-jobs \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"prompt_id":<id>,"platform":"deepseek","samples":1}'
docker logs geo-crawler --since 5m 2>&1 | tail -50
```

### 4.3 计数与明细

```bash
curl -s -H "X-API-Key: $KEY" \
  "http://127.0.0.1:8200/v1/counts?brand_id=34&platform=deepseek"
curl -s -H "X-API-Key: $KEY" \
  "http://127.0.0.1:8200/v1/responses?limit=5"
```

### 4.4 数据脚本（API 容器内）

```bash
docker exec geo-api python -m app.scripts.verify_l2 --brand-id 34
docker exec geo-api python -m app.scripts.data_governance_min --dry-run
# 确认后再去掉 --dry-run
```

### 4.5 测试

```bash
# 本机（无 DB 集成项会 skip）
cd apps/api && PYTHONPATH=. pytest tests/ -q
cd packages/metrics && pytest -q

# VPS 全量（示例）
docker exec -w /app/apps/api -e PYTHONPATH=. \
  -e GEO_TEST_DATABASE_URL="postgresql+psycopg://geo:geo@postgres:5432/geo" \
  geo-api python -m pytest tests/ -q
```

---

## 5. Compose 环境变量（要点）

见仓库根 `.env.example` / `deploy` 环境：

| 变量 | 含义 |
|------|------|
| `DATABASE_URL` | API/crawler 连 Postgres |
| `API_KEY` | 公网鉴权 |
| `API_COOKIE_SECURE` | HTTPS 后 Cookie Secure |
| `CRAWL_MODE` | `real` / `fake` |
| `FAKE_WORKER_ENABLED` | API 内嵌假 worker；真抓时建议 `false` 防双领任务 |
| `DEEPSEEK_STORAGE_STATE` | storage_state 路径 |
| `SCREENSHOT_DIR` | 默认 `/data/screenshots` |
| `PLAYWRIGHT_HEADLESS` | 默认 true |
| `CRAWL_TIMEOUT_MS` | 抓取超时 |

生产真抓典型：`CRAWL_MODE=real`，`FAKE_WORKER_ENABLED=false`，crawler profile 开启。

---

## 6. 故障速查

| 现象 | 排查 |
|------|------|
| `missing or invalid API key` | 头未带 Key / `.env` 未进容器 |
| 任务一直 pending | `geo-crawler` 是否 Up；`CRAWL_MODE`；日志 |
| 登录墙 / 空答 | storage_state 是否有效；重新导出并 `docker cp` |
| 截图侧栏/输入框 | 是否旧镜像；日志有无 `clean-render`；重建 crawler |
| counts 命中异常 | 是否含 fake；`answer_status`；别名是否过宽（如裸 `361`） |
| push 后代码没变 | deploy 日志；容器是否 rebuild；worktree 与 image 是否一致 |
| running 僵死 | 查 jobs 表；依赖代码内回收；必要时 retry |

```bash
docker logs geo-api --since 30m 2>&1 | tail -80
docker logs geo-crawler --since 30m 2>&1 | tail -80
docker exec geo-postgres psql -U geo -d geo \
  -c "select id,status,error_message from crawl_jobs order by id desc limit 10;"
```

---

## 7. 安全清单

- [ ] `API_KEY` 已设且足够长  
- [ ] `.env`、`*.pem`、`deepseek_storage.json` 在 `.gitignore`  
- [ ] Postgres 仅 `127.0.0.1`  
- [ ] 不把 Key 写进前端仓库明文（写操作由用户/服务端保管）  
- [ ] 不在日志中打印 storage_state 全文  

---

## 8. Git 约定（后端改动）

```text
feat(api|crawl|metrics): 新能力
fix(api|crawl): 修 bug
docs: 仅文档
chore: 杂项/依赖
```

- 一步一 commit，说明写清「为什么」  
- push `main` 即部署；小心高峰时 rebuild crawler 耗时  
- 不在 commit 中夹带密钥与大体截图二进制  

---

## 9. 文档策略

| 路径 | 用途 |
|------|------|
| `docs/BACKEND.md` | 后端产品/规格（活文档） |
| `docs/BACKEND-RUNBOOK.md` | 本手册（活文档） |
| `docs/archive/*` | 历史 B 步、L3 草案、踩坑长文 — **默认不更新** |

前端产品说明不放本目录扩写；对接只引用 `BACKEND.md` §5–§8。
