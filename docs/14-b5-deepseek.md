# B5 — DeepSeek Web 真抓取

## 开源对照（只学模式，自写代码）

| 项目 | 借鉴点 |
|------|--------|
| [daijinma/geo_marketing](https://github.com/daijinma/geo_marketing) | Playwright；拦截 chat completion / SSE 拼回答；登录态目录 |
| [xxxbozzz/gitgeo](https://github.com/xxxbozzz/gitgeo) | `platform → url/选择器` 配置表；DeepSeek `chat.deepseek.com` + textarea / `.ds-markdown` |

**未整段复制**无 License 源码；实现见 `apps/api/app/providers/deepseek_web.py`。

## 模式

| `CRAWL_MODE` | 行为 |
|--------------|------|
| `fake`（默认） | 假 L0（B3），不需浏览器 |
| `real` | DeepSeek Web（需 Playwright + 通常需登录态） |

## 登录态（真抓必需）

DeepSeek 网页多数情况要登录。准备 `storage_state` JSON：

```bash
# 在有图形界面的机器上一次性导出（示例）
# playwright codegen 或自写脚本 storage_state 保存到 deepseek_storage.json
```

放到 VPS：

```bash
# 写入 crawler volume 或挂载
docker cp deepseek_storage.json geo-crawler:/data/deepseek_storage.json
```

## 启动真抓取 Worker（VPS）

```bash
cd /opt/geo-demo/deploy
export CRAWL_MODE=real
export FAKE_WORKER_ENABLED=false   # API 内建 worker 关掉，避免抢任务
docker compose --profile crawl up -d --build crawler
docker compose up -d api
docker logs -f geo-crawler
```

创建任务：

```bash
curl -s -X POST http://127.0.0.1:8200/v1/crawl-jobs \
  -H 'Content-Type: application/json' \
  -d '{"prompt_id":1,"platform":"deepseek","samples":1}'
```

失败常见原因：`DeepSeek appears to require login` → 配置 `DEEPSEEK_STORAGE_STATE`。

## 流水线

```text
crawl_job pending → provider.search → raw_responses + citations (L0) → L1 annotate
```

## 非目标

- 豆包/Kimi（后续平台）
- LLM 情感（后置）
- 账号池 / 代理池规模化


## 登录时机（什么时候登录？）

**不是**每条任务登录一次。

| 时机 | 做什么 |
|------|--------|
| **首次启用真抓之前（一次性）** | 在浏览器登录 DeepSeek，导出 Playwright `storage_state` JSON |
| **部署时** | 把 JSON 放到 crawler 的 `DEEPSEEK_STORAGE_STATE`（如 `/data/deepseek_storage.json`） |
| **日常跑 crawl_job** | Worker 自动带登录态打开页面；**无需再登录** |
| **登录过期 / 任务大量 failed 且报 login** | 重新导出 storage_state 并替换文件，重启 crawler |

推荐流程：

```text
1. 本机/有界面环境登录 DeepSeek → 保存 storage_state
2. 上传到 VPS crawler volume
3. CRAWL_MODE=real + 启动 geo-crawler
4. 之后只调 API 建任务即可
```

假数据模式（`CRAWL_MODE=fake`）**完全不需要**登录。

## Chrome 已登录桥接（本机跑通真回答）

当 VPS Playwright 没有 storage_state 时，可用 **本机已登录 Chrome** 抓到回答后：

```bash
POST /v1/ingest/l0
```

body 含 `prompt_id` + `full_text`（+ 可选 citations），服务端会建 success job、写 L0、跑 L1。

这是当前最稳的「已登录就先跑通」路径。


## 独立 Playwright 导出 storage_state（推荐 · 不碰主 Chrome）

```bash
cd /Users/xiagao/Desktop/geo-demo
apps/api/.venv/bin/python scripts/export_deepseek_storage.py
# 独立窗口登录 DeepSeek → 终端回车
./scripts/deploy_deepseek_storage_to_vps.sh
```

- 不使用日常 Chrome，不读 Chrome Safe Storage 钥匙串
- 生成 `deploy/deepseek_storage.json`（已 gitignore）
- VPS: `CRAWL_MODE=real` + crawler 容器挂载该文件


## 截图证据结构（目标形态）

理想证据图应接近「对话导出」而不是「浏览器整页缩略」：

1. **含问题气泡**（用户问句）
2. **含完整助手回答**（表格/列表/引用角标都在）
3. **无左侧历史栏、无底部输入框**
4. 长回答用 **主列 clip + 纵向拼接**，避免只截一屏

实现：`providers/deepseek_web.py` → `_capture_answer_evidence`


## 截图实现（按全页面截图说明）

参考 `docs/17-playwright-fullpage-screenshot.md`：

1. 隐藏侧栏/输入框（避免 fullPage 拼进无关 chrome）
2. **先滚动整页触发懒加载**
3. 滚回顶部
4. **`page.screenshot(full_page=True)`** 截取滚动范围内全部内容
5. 若仍过短，再用回答节点 element 截图补高
