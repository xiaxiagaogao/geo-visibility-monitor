# B3 — 抓取任务 + 假 Worker（L0）

## 目标

不打开浏览器，跑通：

`创建 crawl_job (pending) → worker → raw_responses + citations (L0) → success`

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/v1/crawl-jobs` | body: `prompt_id`, `platform`(默认 deepseek), `samples` |
| GET | `/v1/crawl-jobs` | `?status=&platform=&prompt_id=` |
| GET | `/v1/crawl-jobs/{id}` | 含关联 response |
| POST | `/v1/crawl-jobs/{id}/retry` | 失败/成功可重新入队 |
| POST | `/v1/crawl-jobs/worker/run-once` | 手动跑一批 pending |
| GET | `/v1/responses` | L0 列表 |
| GET | `/v1/responses/{id}` | L0 详情+citations |

## Worker

- 默认 **API 进程内后台线程** 轮询 `pending`（`FAKE_WORKER_ENABLED=true`）
- 状态机：`pending → running → success|failed`
- 假正文会**交替**写「提到品牌 / 不提品牌」，便于以后 B4 标注

## 验收

```bash
BASE=http://96.9.213.230:8200
# 创建任务（prompt_id=1）
curl -s -X POST $BASE/v1/crawl-jobs -H 'Content-Type: application/json' \
  -d '{"prompt_id":1,"platform":"deepseek","samples":2}'
# 等 2–5 秒或手动
curl -s -X POST "$BASE/v1/crawl-jobs/worker/run-once"
curl -s $BASE/v1/responses | python3 -m json.tool | head
```

## 非目标（B3 不做）

- 真 Playwright / DeepSeek（B5）
- L1 标注落库（B4）
- counts API（B6）
