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
