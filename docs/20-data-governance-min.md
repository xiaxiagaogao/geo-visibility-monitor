# 最小数据治理（L2 后 / L3 前）

> 日期：2026-07-31  
> 状态：**已完成（VPS 2026-07-31）** → 可进 L3  
> 范围：**短步**，不做多平台、不做前端

---

## 目标

让 L2 counts / 后续 L3 看板 **不被假数据与脏抓污染**。

## 做了什么

| 动作 | 说明 |
|------|------|
| 删除历史 fake | `raw_json.source` 为 `fake_*` 或正文以 `【假数据` 开头 |
| 脏抓移出分母 | 侧栏误抓（`开启新对话` 开头等）→ `answer_status=error`（重跑 L1） |
| counts 默认排除 fake | `include_fake=false`（默认）；可选 `source=deepseek_web` |
| fake worker | 保持 `FAKE_WORKER_ENABLED=false` / `CRAWL_MODE=real` |
| 空 job 清理 | 无 response 的 crawl_jobs 删除 |

## 不做（明确）

- 不扩第二平台  
- 不改 L3 前端  
- 不强行重抓全部历史截图  
- 不扩品牌别名（另步）

## 命令

```bash
# API 容器内
python -m app.scripts.data_governance_min --dry-run
python -m app.scripts.data_governance_min
python -m app.scripts.verify_l2 --brand-id 1 --platform deepseek --prompt-id 1

# counts
curl -s 'http://127.0.0.1:8200/v1/counts?brand_id=1&prompt_id=1&platform=deepseek'
# 显式只要真抓
curl -s 'http://127.0.0.1:8200/v1/counts?brand_id=1&source=deepseek_web'
```

## 验收

- fake 行数 = 0  
- `n_valid` 不再含侧栏脏抓  
- `verify_l2` PASS  
- 本品 `m_mentioned` 在默认口径下 **不因 fake 虚高**

## 执行结果（VPS）

| 项 | 结果 |
|----|------|
| 删除 fake | response `#1–#5` |
| 侧栏脏抓 | `#7/#8` → `answer_status=error` |
| 空 job | 已删一批无 response 的 crawl_jobs |
| 剩余 | 13 条（chrome_bridge 1 + deepseek_web 12） |
| n_valid | **11**（error 2 不进分母） |
| 土巴兔 m_mentioned | **0**（假数据虚高已消除） |
| verify_l2 | **PASS** |
| commit | `fe78c4d` |

说明：真抓样本当前未命中「土巴兔」别名，L3 上将看到 0% 提及率——这是真实口径，不是计数 bug。
