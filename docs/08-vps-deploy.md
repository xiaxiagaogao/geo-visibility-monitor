# VPS 部署流程（本地写代码 → git push → 公网机器跑）

> 背景：本机 Docker 不可用；运行与验收在 VPS 上进行。  
> **生产机上已有其他服务**（nginx 80/443、sillytavern:8100、dashboard:8090）。geo-demo 必须隔离端口与目录。

---

## 1. 机器信息（本项目）

| 项 | 值 |
|----|-----|
| 主机 | `96.9.213.230` |
| 系统 | Ubuntu 24.04，已有 Docker / Compose / nginx / git / Python3.12 |
| 部署目录（工作树） | `/opt/geo-demo` |
| 裸仓库（接收 push） | `/opt/geo-demo.git` |
| SSH 私钥（仅你本机） | 例如 `~/Desktop/pem/SG-DC1.pem`（**禁止提交到 Git**） |

---

## 2. 端口与隔离策略

| 服务 | 绑定 | 说明 |
|------|------|------|
| geo postgres | `127.0.0.1:5433` | **不公网暴露** |
| geo redis（可选 profile） | `127.0.0.1:6380` | 不公网暴露 |
| geo API（后续） | 建议 `127.0.0.1:8200` + nginx 反代，或 `0.0.0.0:8200` 临时调试 | **避开** 80/443/8090/8100 |
| 现有 sillytavern | 8100 | 不动 |
| 现有 dashboard | 127.0.0.1:8090 | 不动 |

公网访问后续通过 nginx 反代到 API，而不是直接开数据库端口。

---

## 3. 日常开发流（你要记住的闭环）

```text
本机改代码
  → git status / git add / git commit
  → git push vps main
  → VPS post-receive hook 自动 checkout 到 /opt/geo-demo
  → 自动 docker compose up 相关服务
  → 你用公网（或 SSH）验收
```

本机**不要求**跑 Docker / pytest 连库（你已决定本地不测运行时）。

---

## 4. 本机一次性配置 remote

```bash
cd /Users/xiagao/Desktop/geo-demo

# 私钥权限
chmod 400 /Users/xiagao/Desktop/pem/SG-DC1.pem

# 推送时使用该密钥（可写进 ~/.zshrc）
export GIT_SSH_COMMAND='ssh -i /Users/xiagao/Desktop/pem/SG-DC1.pem -o IdentitiesOnly=yes'

# 添加远程（只需一次）
git remote add vps root@96.9.213.230:/opt/geo-demo.git
# 若已存在：git remote set-url vps root@96.9.213.230:/opt/geo-demo.git

git remote -v
git push -u vps main
```

可选：仓库内辅助脚本 `scripts/push-vps.sh`（见仓库）。

---

## 5. VPS 上 hook 做了什么

`/opt/geo-demo.git/hooks/post-receive`：

1. 强制 checkout `main` → `/opt/geo-demo`
2. `cd /opt/geo-demo/deploy && docker compose up -d postgres`
3. 打印 `docker compose ps` 与简单表检查

改 hook 需要 SSH 上机编辑（不通过业务代码频繁改也行）。

---

## 6. 验收命令（SSH 上机）

```bash
ssh -i /Users/xiagao/Desktop/pem/SG-DC1.pem root@96.9.213.230

docker ps --filter name=geo-
docker exec geo-postgres psql -U geo -d geo -c '\dt'
docker exec geo-postgres psql -U geo -d geo -c "SELECT id FROM schema_migrations;"
```

在 VPS 上跑 API 校验（后续）：

```bash
cd /opt/geo-demo/apps/api
python3 -m venv .venv
source .venv/bin/activate
pip install -e ../../packages/metrics -e .
export DATABASE_URL=postgresql+psycopg://geo:geo@127.0.0.1:5433/geo
python -m app.scripts.verify_db
```

---

## 7. 安全注意（生产机）

1. **私钥不要进 Git、不要发聊天群。**  
2. **Postgres 不要改成 0.0.0.0:5432 公网映射。**  
3. 默认密码 `geo/geo` 仅学习/初期；正式对外前务必改强密码与 `.env`。  
4. 改 VPS 时避免 `docker compose down` 误伤其他项目目录。  
5. 现有 nginx / sillytavern / dashboard **不要删**。

---

## 8. 故障排查

| 现象 | 处理 |
|------|------|
| `Permission denied (publickey)` | 检查 `GIT_SSH_COMMAND` 与 pem 权限 `400` |
| push 被拒 | 是否推送到 `main`；hook 是否可执行 `chmod +x hooks/post-receive` |
| 容器起不来 | `docker logs geo-postgres`；端口 5433 是否被占 |
| 表不存在 | 数据卷是旧空卷？`docker compose down` 后不要随便 `-v`；或进容器查 init 日志 |

---

## 9. 修订

| 日期 | 说明 |
|------|------|
| 2026-07-30 | 初版：改 VPS 运行时；本地不测 Docker |
