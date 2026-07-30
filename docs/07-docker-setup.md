# Docker 安装与本机验收（macOS）

> 目标：能用 `docker` / `docker compose` 启动 `deploy/postgres`，完成 B1 真库验收。

---

## 1. 当前状态（2026-07-30）

| 项 | 状态 |
|----|------|
| Docker.app | 已安装到 `/Applications/Docker.app` |
| CLI | `docker version` 可用（约 29.x） |
| 引擎（daemon） | **可能尚未就绪**；首次启动需你在图形界面完成授权 |
| Homebrew cask 完整安装 | 因写入 `/usr/local/bin` 需要 **sudo 密码** 失败；已改用 **手动安装 App + 用户目录 CLI 链接** |

用户级 CLI 链接（无需 sudo）：

```bash
# 已链接到：
~/.local/bin/docker
~/.local/bin/docker-compose   # 如已创建
# 以及 Docker.app 内置：
/Applications/Docker.app/Contents/Resources/bin/docker
```

建议把下面放进 `~/.zshrc`（若还没有）：

```bash
export PATH="$HOME/.local/bin:/Applications/Docker.app/Contents/Resources/bin:$PATH"
```

然后：

```bash
source ~/.zshrc
docker --version
```

---

## 2. 你需要在本机完成的「首次启动」（必须人手点一下）

1. 打开 **启动台 / 应用程序** 里的 **Docker**（或终端执行 `open -a Docker`）。
2. 若弹出：
   - 许可协议 → **Accept**
   - 需要密码 / 辅助功能 / 完全磁盘访问等 → **按提示允许**
   - 是否使用推荐设置 → 默认即可
3. 菜单栏出现 Docker 鲸鱼图标，且显示 **Engine running / Docker Desktop is running**。
4. 终端验证：

```bash
docker info | head -30
# 应能看到 Server Version，而不是 "unable to start"
```

若一直 `Docker Desktop is unable to start`：

- 打开 Docker Desktop → Troubleshoot → **Restart**
- 系统设置 → 隐私与安全性 → 看是否有被拦截的扩展
- 重启 Mac 后再开 Docker（Apple Silicon 上偶发）

---

## 3. 用 Docker 验收 B1（引擎就绪后）

```bash
cd /Users/xiagao/Desktop/geo-demo/deploy
docker compose up -d postgres
docker compose ps
docker compose exec postgres psql -U geo -d geo -c '\dt'

cd ../apps/api
source .venv/bin/activate   # 若尚未建 venv 见 docs/06-b1-database.md
python -m app.scripts.verify_db
```

期望输出包含：`all required tables present`。

停止（数据仍在 volume）：

```bash
cd /Users/xiagao/Desktop/geo-demo/deploy
docker compose stop
```

清空数据重来（会删库！）：

```bash
docker compose down -v
docker compose up -d postgres
```

---

## 4. 若更想用 Homebrew 官方方式（可选）

需要你在**本机终端**输入登录密码（sudo）：

```bash
export PATH="/opt/homebrew/bin:$PATH"
brew install --cask docker-desktop
```

成功后同样 `open -a Docker` 完成首次设置。

---

## 5. 和 Git / 后端步骤的关系

- Docker 只是运行 Postgres 的环境，**不是业务代码**。
- B1 代码已在 Git；你完成引擎启动 + `verify_db` 后，B1 **真库验收** 才算闭环。
- 通过后告诉我，我们再开 **B2**。
