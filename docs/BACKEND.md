# GEO Demo · 后端核心说明

> **后端唯一现行文档**（由历史 01–27 提炼：保留现行有效约定，去掉过时/错误/重复与前端草案）。  
> 原材料在 `history/docs-archive/`，**冲突时以本文 + 代码为准**。  
> 前端另成产品、另写文档；本文只约定后端职责与对接契约。

---

## 1. 定位

| 项 | 约定 |
|----|------|
| 项目 | 个人学习用 GEO **可见性监测**，非商用 SaaS |
| 后端产品 | 配置监测对象 → 抓取 AI 回答 → L1 标注 → **L2 计数 API** + 明细/证据查询 |
| 前端产品 | 展示与比率/图表（**不在本文展开**） |
| 运行方式 | **本机只写代码**；**VPS 跑** API / crawler / Postgres |
| 首发平台 | DeepSeek Web；豆包等后置 |

**后端不做：** 返回提及率/SoV 当权威、浏览器 LLM、多租户计费、账号池、内容生成。  
**`/qa`：** 运维质检页，不是正式产品前端。

---

## 2. 指标分层（拍板，勿再改口径）

```text
L0 原文/引用/截图     → 后端存储
L1 单次判定           → 后端规则标注（可版本化重跑）
L2 整数计数           → 后端 GET /v1/counts（实时聚合；日表物化后置）
L3 比率/综合分/趋势   → 前端用 counts 相除（默认不落库）
```

| 规则 | 说明 |
|------|------|
| 分母 | 仅 `answer_status = ok` → `n_valid` |
| 分子 | `mentions` 上 `m_mentioned` / 类型 / 位置桶等 **整数** |
| 假数据 | counts 默认 `include_fake=false` |
| `metric_snapshots` | 表可存在，**MVP 不当 L2 真相源** |
| 综合分权重 | 可经 `/v1/config/metrics` 下发，**计算在前端** |
| 情感 | 若做：后端 L1 后置；**禁止前端调 LLM** |

**公式（前端侧，便于联调）：**  
`提及率 = m_mentioned / n_valid`；`SoV = m_本品 / (m_本品 + Σ m_竞品)`；`n_valid=0` 或 SoV 分母为 0 时显示不可用。

---

## 3. 域模型（要点）

```text
Brand ──< Alias
Brand ──< CompetitorLink >── Brand
Brand ──< Prompt ──< CrawlJob ──< RawResponse
RawResponse ──< Mention（每回答×每品牌唯一）
RawResponse ──< Citation
```

| 表 | 层 | 要点 |
|----|----|------|
| brands / brand_aliases / competitor_links | 配置 | 别名勿过宽（见 §6） |
| prompts | 配置 | 监测提问；**正文不应含监测品牌名**（见 §6） |
| crawl_jobs | 采集 | pending → running → success/failed |
| raw_responses | L0+L1 | `full_text` 必须是**原文**；`answer_status`；`annotator_version` |
| mentions | L1 | mentioned / mention_type / position_bucket / evidence… |
| citations | L0 | 解析质量随平台变化 |

**answer_status：** `ok` \| `empty` \| `too_short` \| `error`  
（侧栏误抓、明确假数据等 → `error`，不进分母。）

**mention_type：** `body` \| `citation_only` \| `none`  
**position_bucket：** 按**首次**提及 offset → `head` / `middle` / `tail`（当前 annotator：`l1-rules-v2`）。

---

## 4. API 地图

Base：`http://<host>:8200`。字段以代码 `apps/api/app/api/*` 为准。

| 域 | 方法 | 路径 |
|----|------|------|
| 健康 | GET | `/health` · `/health/db` |
| 品牌 | CRUD | `/v1/brands` · `/v1/brands/{id}` |
| Prompt | CRUD | `/v1/prompts` · `/v1/prompts/{id}` |
| 任务 | GET/POST | `/v1/crawl-jobs` · `/{id}` · `/{id}/retry` · `/worker/run-once` |
| 明细 | GET | `/v1/responses` · `/{id}` |
| 重标 | POST | `/v1/responses/{id}/annotate` · `/annotate/run` |
| 计数 | GET | `/v1/counts` |
| 口径 | GET | `/v1/config/metrics` |
| 灌入 | POST | `/v1/ingest/l0`（非主路径） |
| 截图 | GET | `/v1/media/screenshots/{file}` |
| 质检 | GET/POST | `/qa` · `/qa/login` · `/qa/responses`… |

### `/v1/counts`（L2）

| 参数 | 说明 |
|------|------|
| `brand_id` | 必填（监测主品牌） |
| `platform` / `prompt_id` / `from` / `to` | 过滤；`to` **含当天末** |
| `group_by` | `none` \| `day` \| `platform` \| `prompt` |
| `include_fake` | 默认 `false` |
| `source` | 可选，如 `deepseek_web` |

**不做：** `category` 过滤参数（前端读 `/v1/prompts` 自行归类）。  
**不做：** API 直接返回提及率等比率权威字段。

---

## 5. 鉴权

| 通道 | 范围 |
|------|------|
| `X-API-Key` / `Authorization: Bearer` | **所有方法** |
| Cookie `geo_qa_key`（`/qa/login`） | **仅 GET/HEAD/OPTIONS** |

- 截图 `<img>` 不能带自定义头 → 读接口允许 Cookie。  
- Cookie **禁止**用于写 → 防 CSRF（有测试约束，勿放开）。  
- 公网必须配置 `API_KEY`（`deploy/.env`）；空 key = 无鉴权（仅本机）。

---

## 6. 监测数据口径（从实践收束）

### 6.1 提问词

- **禁止**「安踏和李宁哪个好」这类**点名本品**的题 → 提及率虚高，测不到可见性。  
- 应用无提示品类/场景题，例如「国产运动鞋品牌有哪些值得买的？」。

### 6.2 别名

- 勿用裸 `361`（数字误匹配）；用 `361°` / `361度`。  
- 集团子品牌是否计入本品要单独定口径，勿与主品牌混算（例：安踏 vs 斐乐/迪桑特）。

### 6.3 现网演示集（可并存）

| 集 | 用途 |
|----|------|
| **安踏 + 竞品**（主演示） | 无提示题；应用来验收比率/SoV 是否「算得出」 |
| 土巴兔等旧集 | 可保留作**零提及** UI / 多品牌切换用例；counts 按 `brand_id` 隔离 |

具体 id 以库内数据为准（种子脚本/历史操作可能变化）；对接时用 API 列表查询。

### 6.4 假数据与脏抓

- 删除或排除 `source=fake*` / 正文 `【假数据`。  
- 侧栏误抓（如「开启新对话」开头）→ `answer_status=error`。

---

## 7. 抓取实现约束（DeepSeek · 易错点）

这些是代码 review / 真抓后的**硬约束**，不是流水账：

| 约束 | 原因 |
|------|------|
| L0 `full_text` **存原文** | 旧逻辑「清洗后写库」会不可逆破坏正文；清洗最多进 `raw_json` |
| **优先 DOM** 取答 | 纯流式拼接会丢首块 |
| 位置 = **首次**提及 | 按别名长度抢先命中会系统性偏 tail |
| offset 必须能对**原文**切片 | 归一化改长度会导致 evidence 错位 |
| 证据截图：抽回答 → 独立页渲染 → full_page | 直接对聊天页 full_page 会带侧栏/输入框 |
| 不落库 DeepSeek 会话 URL | 多会话上下文串扰；证据靠截图 |
| 抓完尽量删会话（侧栏 UI） | 防历史堆积污染 |
| 登录 | `DEEPSEEK_STORAGE_STATE`；禁止提交 Git |
| 僵死 `running` | 超时回收为 failed；允许 retry；勿只捞 pending 永远丢任务 |
| DELETE 品牌/Prompt | 须能处理子行（级联/明确策略），禁止 500 裸崩 |

平台：`deepseek`；source 常见：`deepseek_web`（另有历史 `chrome_bridge` / fake，默认计数排除 fake）。

---

## 8. 前后端契约（后端保证）

1. 展示用指标：**只信** `/v1/counts` 整数，前端自己除。  
2. 下钻：`/v1/responses` + `/v1/media/screenshots/...`。  
3. 写操作必须 Key 头；读可在同源 Cookie 下工作。  
4. 未接入平台不要假定有数据；灰显由前端处理。  
5. 改 L1 规则会升 `annotator_version` → 需重跑 annotate 旧数据才一致。

---

## 9. 组件与目录

| 组件 | 说明 |
|------|------|
| `apps/api` | FastAPI + worker 入口 |
| `geo-crawler` | Playwright 真抓 |
| `geo-postgres` | 数据 |
| `packages/metrics` | 匹配/分桶纯逻辑 + 单测 |
| `deploy/` | compose、Dockerfile、hook、init.sql |

```text
本机 push main → VPS post-receive → /opt/geo-demo + docker compose
```

---

## 10. 运维速查

| 项 | 值 |
|----|-----|
| VPS | `96.9.213.230` |
| 工作树 / 裸仓 | `/opt/geo-demo` · `/opt/geo-demo.git` |
| API | `:8200`（需 Key） |
| 库 | `127.0.0.1:5433`（勿公网） |
| 日志 | `/var/log/geo-demo-deploy.log` |
| 容器 | `geo-api` · `geo-crawler` · `geo-postgres` |
| 勿碰 | `:8100` sillytavern · `:8090` fund-dashboard |

```bash
# 发布
export GIT_SSH_COMMAND='ssh -i <pem> -o IdentitiesOnly=yes'
git push vps main

# 健康 / 计数（在可访问 API 处）
curl -s -H "X-API-Key: $KEY" http://127.0.0.1:8200/health
curl -s -H "X-API-Key: $KEY" "http://127.0.0.1:8200/v1/counts?brand_id=<id>"

# 建任务
curl -s -X POST http://127.0.0.1:8200/v1/crawl-jobs \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"prompt_id":<id>,"platform":"deepseek","samples":1}'

# 自检
docker exec geo-api python -m app.scripts.verify_l2 --brand-id <id>
cd apps/api && PYTHONPATH=. pytest tests/ -q
cd packages/metrics && pytest -q
```

**环境变量要点：** `DATABASE_URL` · `API_KEY` · `CRAWL_MODE=real` · `FAKE_WORKER_ENABLED=false`（真抓）· `DEEPSEEK_STORAGE_STATE` · `SCREENSHOT_DIR` · `CRAWL_STUCK_JOB_SEC`（僵死回收）。

**故障：** 401→Key；pending 不动→crawler/日志；登录墙→storage_state；截图脏→是否 clean-render 镜像；counts 怪→fake/status/别名。

**密钥、pem、storage_state、截图 bulk：禁止进 Git。**

---

## 11. 从 01–27 文档里刻意丢掉的东西

下列内容**不进入**本文；对应长文已从 `history/docs-archive/` **删除文件**（可用 git 历史找回），避免继续误读。

| 丢弃 | 原因 | 已删归档文件（示例） |
|------|------|----------------------|
| B1–B7 逐步日记、重复验收表 | 已完成；价值已吸收为约束与 API | `06` `09` `12`–`16` |
| 本机 Docker 为主路径的叙述 | 现行是 VPS 运行 | （原 `07` 等） |
| L3 页面/IA/g1geo 排版长文 | 属前端产品，不归后端核心文档 | `21` `22` `23` `25` `27` |
| Playwright 通用/截图长文 | 只保留「我们怎么取证」的约束 | `17` `18` |
| Git 教程长文 | 运维保留 push 必要命令即可 | `05` |
| 架构长文 + 开源项目大表 | 背景材料，非现行规格 | `04` |
| counts 的 category 参数设想 | **已拍板不做** | （散落于多篇，已不收录） |
| 把 rate 写入 metric_snapshots 当权威 | 与分层冲突 | （散落，已不收录） |
| 错误清洗写回 L0 的旧描述 | 已修复为原文优先 | （旧抓取描述，已不收录） |

---

## 12. 维护规则

1. 后端规格**只改这一文件**（或将来明确拆成第 2 份时再拆，禁止再长出 01–27）。  
2. 先改代码与测试，再改本文。  
3. `history/docs-archive/` 默认冻结。  
