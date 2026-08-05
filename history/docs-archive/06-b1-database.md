# B1 — 数据库落地

## 目标

- PostgreSQL schema 与 [02-data-model](./02-data-model.md) 对齐  
- API 能通过 `DATABASE_URL` 连接  
- 一键校验表是否齐全  

## 产物

| 路径 | 说明 |
|------|------|
| `deploy/docker-compose.yml` | `postgres` 服务（`redis` 在 profile `full`） |
| `deploy/init.sql` | 首启自动建表 + `schema_migrations` |
| `apps/api/app/core/config.py` | 环境变量 |
| `apps/api/app/core/db.py` | Engine / Session |
| `apps/api/app/models/entities.py` | SQLAlchemy 模型（供 B2+） |
| `apps/api/app/scripts/verify_db.py` | 连接 + 表检查 |
| `GET /health/db` | 运行时探活 |

## 启动 Postgres

**需要本机 Docker。**

```bash
cd deploy
docker compose up -d postgres
docker compose ps
docker compose exec postgres psql -U geo -d geo -c '\dt'
```

默认连接：

```text
postgresql+psycopg://geo:geo@127.0.0.1:5432/geo
```

复制环境变量：

```bash
cp .env.example .env
```

## 校验

```bash
cd apps/api
python3 -m venv .venv
source .venv/bin/activate
pip install -e "../../packages/metrics"
pip install -e ".[dev]"
python -m app.scripts.verify_db
```

期望：`all required tables present`，exit code 0。

## 验收标准（B1）

- [ ] `docker compose up -d postgres` 成功（或等价自建 PG 并执行 `init.sql`）  
- [ ] `python -m app.scripts.verify_db` 通过  
- [ ] （可选）启动 API 后 `GET /health/db` 返回 `ok: true`  

## 说明

当前开发机若未安装 Docker/Postgres，**代码与脚本仍可提交**；真库验收在你本机装好运行环境后执行。
