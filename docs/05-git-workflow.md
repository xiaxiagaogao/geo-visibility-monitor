# Git 工作流规范（个人学习项目）

## 仓库

- 主分支：`main`
- 远程：按需添加（`git remote add origin <url>`）
- 不要提交：`.env`、虚拟环境、浏览器登录态、截图大数据、密钥

## 提交信息（Conventional Commits 简化）

```text
<type>(<scope>): <简短说明>

类型 type：
  feat     新功能
  fix      修复
  docs     文档
  chore    杂务（工具、依赖、忽略规则）
  refactor 重构
  test     测试
  build    构建/部署

范围 scope 示例：
  api | crawler | metrics | db | deploy | web | docs
```

示例：

```text
feat(db): add PostgreSQL schema and API engine bootstrap
docs(arch): record B7 as backend data preview
chore(git): add workflow conventions
```

## 分支（可选）

个人学习可直接在 `main` 小步提交。若实验性改动：

```text
feat/b1-db
feat/b5-deepseek-provider
```

合并回 `main` 后删除特性分支即可。

## 提交粒度

- 一次提交只做一类事（文档 / 功能 / 杂务分开更佳）
- B 步骤完成时应有可运行的验收说明（写在 commit body 或 docs）

## 推送前自检

```bash
# 指标单测
cd packages/metrics && .venv/bin/python -m pytest -q

# DB 校验（需 Postgres 已启动）
cd apps/api && .venv/bin/python -m app.scripts.verify_db
```
