# Git 工作流规范（中文详细版）

> 项目：geo-demo（个人学习）  
> 目的：每一步「做什么、为什么、怎么敲、怎么检查」都说清楚，避免只会复制命令却不知道含义。

---

## 0. 署名说明（Author）

### 当前仓库实际署名

来自你本机的 **全局 Git 配置**（`~/.gitconfig`），首提记录为：

| 项 | 值 |
|----|-----|
| **user.name** | `xiaxiagaogao` |
| **user.email** | `66161206+xiaxiagaogao@users.noreply.github.com` |

### 这样署名有没有问题？

**一般没问题，而且推荐这样用。**

| 判断点 | 说明 |
|--------|------|
| 名字 | 与 GitHub 用户名一致，历史里能认出是你 |
| 邮箱 | `数字+用户名@users.noreply.github.com` 是 GitHub **官方隐私邮箱**，推到 GitHub 后仍能关联到你的账号，又不会在公开 commit 里暴露私人邮箱 |
| 是否本地伪造 | 否；是全局配置，不是仓库里乱写的 |

### 如何自己再确认一次

```bash
# 看全局署名（对所有仓库默认生效）
git config --global user.name
git config --global user.email

# 看某一仓库是否覆盖了全局（本仓库目前没有 local 覆盖）
cd /Users/xiagao/Desktop/geo-demo
git config --local user.name
git config --local user.email

# 看最近一次提交实际写进历史的作者
git log -1 --format='%an <%ae>'
```

### 如果以后要改署名

```bash
# 只改「之后新提交」的默认署名
git config --global user.name "你的名字"
git config --global user.email "你的邮箱或 GitHub noreply"

# 注意：已经生成的 commit 不会自动改作者。
# 学习项目一般不必改写历史；若必须改最近一次且尚未 push：
# git commit --amend --reset-author
# （改历史有风险，推过远程后更不要随便 amend）
```

### 和 GitHub 的关系

- 推送后，若 email 绑定在你的 GitHub 账号（含 noreply），网页上会显示你的头像/贡献。  
- 本仓库若还没 `git remote`，提交只在本地，署名仍然写在 commit 对象里。

---

## 1. 基本概念（先建立地图）

| 概念 | 白话 |
|------|------|
| **工作区** | 你正在改的磁盘文件 |
| **暂存区（stage）** | `git add` 后，准备进下一次提交的快照 |
| **提交（commit）** | 一次不可变的历史节点，带作者、时间、说明 |
| **分支（branch）** | 指向某次提交的可移动指针；我们主分支叫 `main` |
| **远程（remote）** | 如 GitHub 上的副本；本学习仓可暂不设置 |

日常闭环：

```text
改文件 → git status 查看 → git add 选入暂存 → git commit 记历史
（可选）→ git push 推到 GitHub
```

---

## 2. 本仓库约定

### 2.1 分支

| 分支 | 用途 |
|------|------|
| `main` | 默认主干；个人学习可直接在此小步提交 |
| `feat/xxx` | 可选：实验性大改时再建，完成后再合并回 `main` |

查看当前分支：

```bash
cd /Users/xiagao/Desktop/geo-demo
git branch
# * main  表示当前在 main
```

### 2.2 提交说明格式（Conventional Commits 简化）

```text
<type>(<scope>): <用中文或英文简述做了什么>

可选正文：
- 为什么改
- 怎么验收
```

**type（类型）**

| type | 何时用 | 例子 |
|------|--------|------|
| `feat` | 新功能、新能力 | `feat(db): 落地 PostgreSQL 表结构` |
| `fix` | 修 bug | `fix(api): 修复 /health/db 连接串解析` |
| `docs` | 只改文档 | `docs(git): 补充中文步骤说明` |
| `chore` | 工具、忽略规则、杂务 | `chore(git): 更新 .gitignore` |
| `refactor` | 重构不改对外行为 | `refactor(api): 拆分 models 模块` |
| `test` | 加/改测试 | `test(metrics): 补充 SoV 边界用例` |
| `build` | 构建、依赖、部署脚本 | `build(deploy): 调整 compose 健康检查` |

**scope（范围，可选但推荐）**

`api` | `crawler` | `metrics` | `db` | `deploy` | `web` | `docs` | `git`

### 2.3 绝不提交的内容

- `.env`（真密钥）、虚拟环境 `.venv/`  
- `browser_data/`、大批截图、登录 Cookie  
- `node_modules/`、`__pycache__/`  

由根目录 `.gitignore` 控制；提交前用 `git status` 确认没有这些路径。

---

## 3. 常用命令逐步说明（按使用顺序）

以下均假设：

```bash
cd /Users/xiagao/Desktop/geo-demo
```

---

### 步骤 A：`git status` — 我现在改了什么？

**做什么：** 看工作区与暂存区相对「上次提交」的差异清单。  
**为什么：** 提交前必做，防止漏加文件或误加密钥。

```bash
git status
```

**怎么读输出：**

| 区域文案 | 含义 | 下一步 |
|----------|------|--------|
| `Untracked files` | 新文件，Git 还不跟踪 | 需要则 `git add` |
| `Changes not staged` | 已跟踪文件被改了，但还没进暂存 | `git add` 相关文件 |
| `Changes to be committed` | 已暂存，会进下一次 commit | 可 `git commit` |
| `nothing to commit, working tree clean` | 干净，无未提交改动 | 无需提交 |

**更短列表：**

```bash
git status --short
# 第一列：暂存区状态；第二列：工作区状态
# 例： M = 已修改未暂存；A = 新文件已暂存；?? = 未跟踪
```

---

### 步骤 B：`git diff` — 具体改了哪几行？

**做什么：** 看内容级差异。  
**为什么：** `status` 只告诉你文件名；`diff` 告诉你改动是否符合预期。

```bash
# 工作区 vs 暂存区（还没 add 的改动）
git diff

# 暂存区 vs 上次提交（已经 add、即将 commit 的内容）
git diff --staged
```

---

### 步骤 C：`git add` — 把改动放进暂存区

**做什么：** 选择「下一次提交要包含哪些文件」。  
**为什么：** 一次提交应尽量只做一类事；可以只 add 部分文件。

```bash
# 添加指定文件（推荐，可控）
git add docs/05-git-workflow.md

# 添加某个目录
git add apps/api/

# 添加所有已跟踪的改动 + 未跟踪的新文件（方便但要先 status 确认）
git add -A
```

**检查是否加对了：**

```bash
git status
git diff --staged
```

**加错了，从暂存区撤出（不删文件内容）：**

```bash
git restore --staged 路径/文件
# 旧写法：git reset HEAD 路径/文件
```

---

### 步骤 D：`git commit` — 生成一条历史记录

**做什么：** 把暂存区做成一次 commit。  
**为什么：** 可回溯、可对比、可说明意图。

**推荐写法（信息清晰，适合本项目）：**

```bash
git commit -m "docs(git): 补充中文逐步操作说明"
```

**多行说明（正文写验收方式时）：**

```bash
git commit -m "feat(db): 完成 B1 数据库连接与校验脚本"
```

然后在编辑器里追加正文亦可；或使用：

```bash
git commit
# 会打开编辑器，第一行标题，空一行后写正文
```

**提交后检查：**

```bash
git log -1 --stat
# 应看到：作者署名、说明、变更文件列表
```

**刚刚提交信息写错了（仅限「最后一次」且未 push）：**

```bash
git commit --amend -m "docs(git): 更正后的说明"
```

---

### 步骤 E：`git log` — 浏览历史

```bash
# 简洁图
git log --oneline -10

# 看某次详情
git log -1 --stat

# 看作者与邮箱
git log -5 --format='%h %an <%ae> %s'
```

---

### 步骤 F：`git restore` — 丢弃未提交的修改（危险，慎用）

**做什么：** 把工作区文件恢复成上次提交（或暂存）的样子。  
**为什么：** 改乱了想重来。  
**警告：** 未提交的内容会丢，无法从 Git 找回。

```bash
# 丢弃某个文件的工作区修改（未 add）
git restore 路径/文件

# 清空暂存但保留文件内容（见步骤 C）
git restore --staged 路径/文件
```

---

### 步骤 G：远程仓库（可选，推 GitHub 时再用）

本学习项目可以长期只在本地 Git。若要上 GitHub：

```bash
# 1）在 GitHub 网站新建空仓库（不要勾选自动加 README，避免冲突）

# 2）添加远程（把 URL 换成你的）
git remote add origin git@github.com:你的用户名/geo-demo.git
# 或 HTTPS：
# git remote add origin https://github.com/你的用户名/geo-demo.git

# 3）查看远程是否配置成功
git remote -v

# 4）首次推送并设置上游
git push -u origin main

# 5）之后本地有新 commit 再推
git push
```

**拉取他人/另一台机器的更新：**

```bash
git pull
```

个人单机学习阶段，可能很久都用不到 `pull`。

---

## 4. 推荐日常作业流（复制即用）

每完成一个小功能（例如 B2 告一段落）时：

```bash
cd /Users/xiagao/Desktop/geo-demo

# ① 看改了什么
git status
git diff

# ② 跑相关自检（按模块选）
# packages/metrics:  pytest
# DB:                python -m app.scripts.verify_db

# ③ 暂存（先想清楚要提交哪些）
git add -A
git status

# ④ 提交
git commit -m "feat(api): 完成 B2 品牌与 Prompt CRUD"

# ⑤ 确认历史
git log -1 --stat
```

---

## 5. 本仓库已有历史（方便你对号入座）

| 项 | 值 |
|----|-----|
| 分支 | `main` |
| 首提 | `91ca72e` |
| 说明 | `feat(db): bootstrap monorepo and land B1 PostgreSQL foundation` |
| 作者 | `xiaxiagaogao <66161206+xiaxiagaogao@users.noreply.github.com>` |

之后每完成 B2、B3… 建议 **一步一提**，message 里带上 `B2`/`B3` 方便检索。

---

## 6. 和「后端步骤 B1…」的关系

| 后端步骤 | Git 上建议 |
|----------|------------|
| 做完可验收的一小步 | `git add` + `git commit` |
| 只改文档 | `docs(...)` |
| 中途半成品、明天继续 | 也可先 commit，说明写清楚做到哪 |
| 大爆炸一次提交全部 B2–B5 | **不推荐**；难回滚、难读历史 |

---

## 7. 常见问题

**Q：`git commit` 提示 configure user.email？**  
A：执行第 0 节的 `git config --global user.name/email`。

**Q：为什么有的文件 `status` 看不见？**  
A：可能被 `.gitignore` 忽略了（如 `.venv`），这是正常且正确的。

**Q：一定要 push 吗？**  
A：学习项目不强制；有备份/多设备/求职展示需求再 push。

**Q：commit 能当备份吗？**  
A：本地 commit 防「改坏了可回退」；硬盘损坏仍可能丢，重要内容再加远程或 Time Machine。

---

## 8. 修订记录

| 日期 | 说明 |
|------|------|
| 2026-07-30 | 初版约定 |
| 2026-07-30 | 扩写中文逐步说明；补充署名核查与 GitHub noreply 说明 |
