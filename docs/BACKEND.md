# GEO Demo · 后端核心说明

> **后端唯一现行文档**（由历史 01–27 全部提炼而成，归档已删除）。  
> **冲突时以本文 + 代码为准**；本文与代码冲突时以代码为准，并回来改本文。  
> 前端另成产品、另写文档；本文只约定后端职责与对接契约。

---

## 1. 定位

| 项 | 约定 |
|----|------|
| 项目 | GEO **可见性监测**。学习项目，但**按商业级系统设计** —— 不拿「这是 demo」当简化理由 |
| 后端产品 | 配置监测对象 → 抓取 AI 回答 → L1 标注 → **L2 计数 API** + 明细/证据查询 |
| 前端产品 | 给**运营**用的检测工具（不是单品牌看板）；展示与比率/图表**不在本文展开** |
| 运行方式 | **本机只写代码**；**VPS 跑** API / crawler / Postgres |
| 首发平台 | DeepSeek Web；豆包 / Kimi / 通义后置 |

**后端不做：** 返回提及率/SoV 当权威、浏览器调 LLM、账号池规模化、内容生成与发布、
告警中心 / 周报 PDF / Webhook。

**后端尚未做、但已列入方向：** 用户体系与三角色权限（超级管理员 / 运营 / 客户）。
当前是**单一共享密钥**（§5），没有 users 表 —— 见 §11「已知债务」。

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
| **presence hit** | `m_mentioned` 计入 **body 与 citation_only 两种**；`m_body` / `m_citation_only` 是它的拆分，不是并列口径 |
| 假数据 | counts 默认 `include_fake=false` |
| `metric_snapshots` | 表可存在（历史占位含 rate 列），**永不当 L2 真相源** |
| 综合分权重 | 可经 `/v1/config/metrics` 下发，**计算在前端** |
| 情感 | 若做：后端 L1 后置；**禁止前端调 LLM** |

**公式（前端侧，便于联调）：**  
`提及率 = m_mentioned / n_valid`；`SoV = m_本品 / (m_本品 + Σ m_竞品)`；`n_valid=0` 或 SoV 分母为 0 时显示不可用。

### 2.1 比率不可加（最容易犯的错）

**任意时间窗的比率 = Σm / Σn，绝不是「日比率的算术平均」。**

分母不等时两者不相等；把日比率存下来再平均，得到的数字没有任何口径。
这条是「后端只给 counts」这个分层的**根本理由** —— 只要前端拿到的是整数，
就不可能在时间窗上算错。

推论：`/v1/counts` 永不返回比率字段；`metric_snapshots` 永不作为权威。

### 2.2 双端一致性

L1 判定在后端 Python（`packages/metrics`），L3 派生在前端 TypeScript。
同一公式两处实现必然漂移，靠三件事约束：

1. **golden fixtures 双边对照** —— 同一组输入，两边算出同一组输出
2. 口径（枚举、默认权重）由 `/v1/config/metrics` 下发，前端不硬编码
3. 版本戳：`annotator_version` 变了就要重跑，否则新旧标注混在一个分母里

**L3 纯函数的入参只接受 counts 整数，不接受比率类型** —— 从类型上堵死「拿比率再算比率」。

---

## 3. 域模型（要点）

字段以 `apps/api/app/models/entities.py` 为准；本节只记**带决策含义**的部分。

```text
Brand ──< Alias
Brand ──< CompetitorLink >── Brand
Brand ──< Prompt ──< CrawlJob ──< RawResponse
RawResponse ──< Mention（每回答×每品牌唯一，DB 有 UNIQUE 约束）
RawResponse ──< Citation
```

| 表 | 层 | 要点 |
|----|----|------|
| brands | 配置 | 有 **`workspace_id`（默认 1）**，`GET /v1/brands` 可按它过滤 —— 目前**唯一的隔离键**，做「客户」角色时是地基。它是最初 `Org → Workspace → Brand` 三层归属模型的残留，上面两层从未建表 |
| brand_aliases / competitor_links | 配置 | 别名勿过宽（见 §6）；竞品**也是 brand 行**，不是字符串 |
| prompts | 配置 | 监测提问；**正文不应含监测品牌名**（见 §6） |
| crawl_jobs | 采集 | pending → running → success/failed；**`sample_index` = 同一 prompt 的第几次采样**。一条 job = **一个样本**，不是一个批次 |
| raw_responses | L0+L1 | `full_text` 必须是**原文**；`answer_status`；`annotator_version` |
| mentions | L1 | 见下方字段说明 |
| citations | L0 | 解析质量随平台变化；联网检索关闭时可能整体为空 |

**没有「批次 / 检测」实体。** 35 个样本 = 35 个 `crawl_jobs` 行。
要「新建一次叫 X 的检测并在列表里回看」，需要新增实体或按 `created_at` 日期分组。

**answer_status：** `ok` \| `empty` \| `too_short` \| `error`  
（侧栏误抓、明确假数据等 → `error`，不进分母。）

**mention_type：** `body` \| `citation_only` \| `none`

**position_bucket：** 按**首次**提及的 offset 把全文三等分  
`head = offset < L/3` · `middle = < 2L/3` · `tail = 其余` · 未提及 = `null`  
（当前 annotator：`l1-rules-v2`）

### 3.1 mentions 有四个列是恒空的

`mentions` 表里这四列**存在但从未被计算**，`annotate.py` 每次写入都硬编码空值：

| 列 | 当前值 | 本该是什么 |
|----|--------|-----------|
| `position_rank` | 恒 `NULL` | 出场顺位或榜单名次 |
| `sentiment` / `sentiment_score` | 恒 `NULL` | 情感（计划由后端接 LLM，L1 后置） |
| `is_recommended` | 恒 `False` | 「推荐/首选/建议选择」启发式 |

`packages/metrics` 里 `score_sentiment()` / `is_recommended()` 的实现是有的，
但只挂在 `/v1/analyze/*` 那两个无状态玩具接口上，**L1 标注流水线没调**。

连带后果：`/v1/counts` 没有 `m_recommended`，**前端算不出推荐率**；
排名、情感相关的一切展示都没有数据源。要用就得先扩 L1 白名单并重跑标注。

### 3.2 offset 与 matched_term 算了但没存

`match_brand()` 返回 `offset` 和 `matched_term`，`annotate.py` 拿它们切出
`evidence_snippet` 之后**直接丢弃**，`mentions` 表没有这两列。

所以「在原文命中处内联高亮品牌名」这个能力，**不是 API 没返回，是库里没存**。
要做需要：加两列 → 改 `annotate` 落库 → `MentionOut` 暴露 → 重跑 annotate。

> 前端**禁止**自己拿 `matched_term` 去正文里重找 —— 会和 L1 口径分叉。

---

## 4. API 地图

Base：`http://<host>:8200`。字段以代码 `apps/api/app/api/*` 为准。

| 域 | 方法 | 路径 |
|----|------|------|
| 根 | GET | `/` → **302 到 `/qa`**（前端要占 `/` 需先改这里） |
| 健康 | GET | `/health`（公开）· `/health/db` · `/health/config`（需 Key，返回 crawl_mode / worker / auth 开关） |
| 品牌 | CRUD | `/v1/brands` · `/v1/brands/{id}` |
| 品牌别名 | PUT | `/v1/brands/{id}/aliases`（整体替换） |
| 竞品关系 | PUT | `/v1/brands/{id}/competitors`（整体替换 id 列表） |
| Prompt | CRUD | `/v1/prompts` · `/v1/prompts/{id}` |
| 任务 | GET/POST | `/v1/crawl-jobs` · `/{id}` · `/{id}/retry` · `/worker/run-once` |
| 明细 | GET | `/v1/responses` · `/{id}` |
| 重标 | POST | `/v1/responses/{id}/annotate` · `/annotate/run` |
| 计数 | GET | `/v1/counts` |
| 口径 | GET | `/v1/config/metrics` |
| 灌入 | POST | `/v1/ingest/l0`（非主路径） |
| 截图 | GET | `/v1/media/screenshots/{file}`（`/qa/media/...` 是同一处理函数的别名） |
| 质检 | GET/POST | `/qa` · `/qa/login` · `/qa/logout` · `/qa/responses`… |
| **勿用** | POST | `/v1/analyze/response` · `/v1/analyze/batch` —— 无状态玩具接口，不读库、不落库，与 L1/L2 口径无关 |

**两个 PUT 是整体替换语义**，不是增量。前端改竞品集合要先读全量再整体提交。

### `/v1/counts`（L2）

| 参数 | 说明 |
|------|------|
| `brand_id` | 必填（监测主品牌） |
| `platform` / `prompt_id` / `from` / `to` | 过滤；`to` **含当天末**（纯日期补到 23:59:59.999999） |
| `group_by` | `none` \| `day` \| `platform` \| `prompt` |
| `include_fake` | 默认 `false` |
| `source` | 可选，如 `deepseek_web` |

**`group_by=prompt` 的 bucket `key` 是 prompt_id 字符串，不是提问文案** ——
要行标题得自己去 `/v1/prompts` 关联。同理 `group_by=day` 的 key 是 **UTC 日期**。

**响应里 `competitors[]` 一律按 `brand_id` 关联，不许按数组下标** —— 顺序不保证。

**不做：** `category` 过滤参数（前端读 `/v1/prompts` 自行归类）。  
**不做：** API 直接返回提及率等比率权威字段。

---

## 5. 鉴权

| 通道 | 范围 |
|------|------|
| `X-API-Key` / `Authorization: Bearer` | **所有方法** |
| Cookie `geo_qa_key`（`POST /qa/login` 下发，`path=/`） | **仅 GET/HEAD/OPTIONS** |
| **完全免鉴权** | `/health` · `/qa/login` · `/favicon.ico` |

- 截图 `<img>` 不能带自定义头 → 读接口允许 Cookie。  
- Cookie **禁止**用于写 → 防 CSRF（`test_cookie_never_works_for_write_methods` 逐方法守着，勿放开）。  
- 未认证且 `Accept: text/html` 的 GET → 302 到 `/qa/login`；否则 401 JSON。  
- 公网必须配置 `API_KEY`（`deploy/.env`，chmod 600）；空 key = **完全无鉴权**，启动打 WARNING。

> **这是「没有用户体系」时的权宜设计。** 按 HTTP 方法切分是用来替代 CSRF token 的。
> 将来做真会话登录与三角色权限时，这条应当被**重新设计**（CSRF token 或
> SameSite=strict + 双提交），而不是原样继承。

---

## 6. 监测数据口径（从实践收束）

### 6.1 提问词

- **禁止**「安踏和李宁哪个好」这类**点名本品**的题 → 提及率必然接近 100%，测不到可见性。  
- 应用无提示品类/场景题，例如「国产运动鞋品牌有哪些值得买的？」。  
- `seed_anta.py` 里有**断言守着这条**：提问词出现监测品牌名直接报错退出。

### 6.2 别名

- 勿用裸 `361`（会匹配正文里任何 361 数字）；用 `361°` / `361度`。  
- 集团子品牌是否计入本品要单独定口径，勿与主品牌混算（例：安踏 vs 斐乐/迪桑特）。
  监测的是**消费者品牌**，不是集团口径；要看集团是另一套指标。

### 6.3 现网演示集（可并存，counts 按 `brand_id` 隔离）

| 集 | 用途 |
|----|------|
| **安踏 + 7 竞品**（主演示） | 无提示题；用来验收比率/SoV 是否「算得出」 |
| 土巴兔等旧集 | **零提及**用例：真抓样本从未命中其别名，L3 上看到 0% 是真实口径**不是 bug** |

具体 id 以库内数据为准；对接时用 API 列表查询。

**基线快照（2026-08-02，`verify_l2 --brand-id 34` PASS）** —— 改 L1 规则重跑后拿它对照：

```text
n_valid = 35（answer_status 全部 ok，零 error）
安踏 m=21 → 60.0%   head 15 / middle 5 / tail 1
竞品区间 14.3%(鸿星尔克 5) ~ 62.9%(亚瑟士 22)
SoV(安踏) = 21 / 137 = 15.3%
```

**这套数据的双峰结构是刻意配比出来的，不是巧合：**

```text
国产 / 性价比 / 篮球类提问   →  安踏 5/5、4/4、3/3、3/3、3/3  （100%）
专业跑鞋 / 健身训练类提问     →  安踏 0/5、0/3                 （0%）
```

全通用向会把本品压到 0%，全国产向会推到 100%，两种极端都看不出趋势。
**60% 是这两极平均出来的** —— 只看总数会掩盖真问题，所以 `group_by=prompt` 是必需能力。

### 6.4 假数据与脏抓

- 删除或排除 `raw_json.source` 为 `fake*` / 正文以 `【假数据` 开头。  
- 侧栏误抓（如「开启新对话」开头）→ `answer_status=error`，不进分母。  
- 治理脚本：`app.scripts.data_governance_min`，**默认 dry-run**（见 §10）。

---

## 7. 抓取实现约束（DeepSeek · 易错点）

这些是代码 review / 真抓后的**硬约束**，不是流水账：

| 约束 | 原因 |
|------|------|
| L0 `full_text` **存原文** | 旧逻辑「清洗后写库」会不可逆破坏正文；清洗结果只进 `raw_json.cleaned_text` |
| **优先 DOM** 取答 | 纯流式拼接会丢首块；`_pick_answer_text` 以 DOM 为真值，stream 只在 DOM 明显更短时兜底 |
| 位置 = **首次**提及 | 按别名长度降序抢先命中会系统性偏 tail |
| offset 必须能对**原文**切片 | 归一化改长度（`strip` / `casefold`）会导致 evidence 错位；用长度守恒的 `_fold()` |
| 证据截图：抽回答 → 独立页渲染 → full_page | 直接对聊天页 full_page 会带侧栏/输入框；渲染页要带 CSP |
| 不落库 DeepSeek 会话 URL | 多会话上下文串扰；证据靠截图 |
| 抓完即删会话（走侧栏 UI） | 防历史堆积污染 DOM 抓取 |
| **删除会话的接口 HTTP 200 不代表删成功** | DeepSeek 把错误放在 body 里（如 `code:40002`）。**验收必须核对真实状态，不能信日志** |
| 清理脚本默认 dry-run | `deepseek_cleanup.py` —— 账号里绝大多数是用户私人对话，误删不可逆 |
| 登录 | `DEEPSEEK_STORAGE_STATE`；禁止提交 Git |
| 僵死 `running` | 超时（`CRAWL_STUCK_JOB_SEC`，默认 600s）回收为 failed；`retry` 放行 running；勿只捞 pending |
| DELETE 品牌/Prompt | ORM 关系须配 `cascade` + `passive_deletes=True`，否则 SQLAlchemy 会先把子表外键置 NULL 而撞 NOT NULL → 500 |

平台：`deepseek`；source 常见：`deepseek_web`（另有历史 `chrome_bridge` / fake，默认计数排除 fake）。

> **存量污染不可回填。** 早期样本的 L0 被旧清洗规则改写过、且丢了首块，
> 重跑 L1 也补不回来 —— 要干净数据只能重抓。安踏那 35 条是修复后抓的，是干净的。

---

## 8. 前后端契约（后端保证）

1. 展示用指标：**只信** `/v1/counts` 整数，前端自己除；时间窗一律 Σm/Σn（§2.1）。  
2. 下钻：`/v1/responses` + `/v1/media/screenshots/...`。  
3. 写操作必须 Key 头；读可在同源 Cookie 下工作（§5）。  
4. 未接入平台不要假定有数据；灰显由前端处理。  
5. 改 L1 规则会升 `annotator_version` → 需重跑 annotate 旧数据才一致。  
6. 排名、情感、推荐率**当前无数据**（§3.1）；前端应走「暂无数据」降级，**不得自行推算**。

---

## 9. 组件与目录

| 组件 | 说明 |
|------|------|
| `apps/api` | FastAPI **和** 抓取 worker（`app.worker_main`）都在这里 |
| `packages/metrics` | 匹配/分桶/情感等纯逻辑 + 单测 |
| `deploy/` | compose、Dockerfile、post-receive hook、init.sql |
| `apps/crawler/` | **死代码**，无人引用 —— `Dockerfile.crawler` 只 COPY `apps/api` + `packages/metrics`，跑的是 `app.worker_main` |

容器：`geo-api` · `geo-crawler` · `geo-postgres`。
**`geo-crawler` 容器跑的是 `apps/api` 的 worker，不是 `apps/crawler/` 目录。**

```text
本机 push main → VPS post-receive（强制 checkout main + docker compose up）→ /opt/geo-demo
```

---

## 10. 运维速查

| 项 | 值 |
|----|-----|
| VPS | `96.9.213.230`（Ubuntu 24.04） |
| 工作树 / 裸仓 | `/opt/geo-demo` · `/opt/geo-demo.git` |
| API | `:8200`（需 Key） |
| 库 | `127.0.0.1:5433`（**勿改 0.0.0.0**；默认口令 `geo/geo` 是弱口令，对外前必须改） |
| 日志 | `/var/log/geo-demo-deploy.log` |
| 容器 | `geo-api` · `geo-crawler` · `geo-postgres` |
| 勿碰 | `:8100` sillytavern · `:8090` fund-dashboard · 现有 nginx |

```bash
# 一次性：配置 push 远端
export GIT_SSH_COMMAND='ssh -i <pem> -o IdentitiesOnly=yes'   # pem 需 chmod 400
git remote add vps root@96.9.213.230:/opt/geo-demo.git

# 发布（post-receive 自动 build + up）
git push vps main

# 健康 / 计数（在可访问 API 处）
curl -s -H "X-API-Key: $KEY" http://127.0.0.1:8200/health
curl -s -H "X-API-Key: $KEY" "http://127.0.0.1:8200/v1/counts?brand_id=<id>"

# 建任务
curl -s -X POST http://127.0.0.1:8200/v1/crawl-jobs \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"prompt_id":<id>,"platform":"deepseek","samples":1}'

# 改了 L1 规则后重跑标注（反复跑到 processed=0）
curl -s -X POST -H "X-API-Key: $KEY" \
  'http://127.0.0.1:8200/v1/responses/annotate/run?limit=500'

# 数据治理（默认 dry-run，确认后去掉 --dry-run）
docker exec geo-api python -m app.scripts.data_governance_min --dry-run

# 自检
docker exec geo-api python -m app.scripts.verify_l2 --brand-id <id>
cd apps/api && PYTHONPATH=. pytest tests/ -q       # 需真库的用例会 skip
cd packages/metrics && pytest -q

# 需真库的用例（在 VPS 容器内跑全套）
docker exec geo-api pip install -q pytest httpx    # 生产镜像不含 dev 依赖，重建后要重装
docker exec -w /app/apps/api -e PYTHONPATH=. \
  -e GEO_TEST_DATABASE_URL="postgresql+psycopg://geo:geo@postgres:5432/geo" \
  geo-api python -m pytest tests/ -q
```

**环境变量要点：** `DATABASE_URL` · `API_KEY` · `CRAWL_MODE=real` · `FAKE_WORKER_ENABLED=false`（真抓）· `DEEPSEEK_STORAGE_STATE` · `SCREENSHOT_DIR` · `CRAWL_STUCK_JOB_SEC`（僵死回收）。

**故障：** 401→Key；pending 不动→crawler/日志；登录墙→storage_state；截图脏→是否 clean-render 镜像；counts 怪→fake/status/别名。

**密钥、pem、storage_state、截图 bulk：禁止进 Git。**

---

## 11. 已知债务（现行代码的真实状态，不是待办清单）

| 债 | 现状 | 何时会咬人 |
|----|------|-----------|
| **无用户体系** | 单一共享密钥，无 users 表，无归属校验 —— `/v1/counts?brand_id=任意值` 谁都能查 | 做三角色权限时。隔离键 `workspace_id` 已存在但未启用（§3） |
| **counts 全量加载** | 把所有 `RawResponse`（含 `full_text` 全文）拉进 Python 再累加，不是 SQL 聚合 | 样本量上千后 |
| **L1 白名单只有一半** | `position_rank` / `sentiment` / `is_recommended` 恒空（§3.1） | 前端要排名、情感、推荐率时 |
| **offset 未落库** | 算了就丢（§3.2） | 要做原文命中高亮时 |
| **无批次 / 提问集实体** | 一条 job = 一个样本，「一次检测」不存在（§3）。最初设计里有 `PromptSet`，与 `Organization` / `Workspace` 一样从未建表 | 要「新建一次命名检测并回看」时 |
| `ensure_schema` 按 `;` 裸切 SQL | 当前迁移能跑；加函数/触发器会碎 | 写复杂迁移时 |
| `verify_l2.py` 误报 | 改过 `competitor_links` 后，残留的旧 mention 行会让 SQL 侧多出品牌分组，比对报 FAIL | 调整竞品集合后 |
| `apps/crawler/` 死代码 | 整目录无人引用（§9） | 读代码的人会被误导 |

---

## 12. 从历史 01–27 里刻意丢掉的东西

历史文档已**全部删除**（`git log` 可找回），要点已提炼进本文。下列内容**刻意不收**：

| 丢弃 | 原因 |
|------|------|
| B1–B7 逐步实施日记、逐步验收表 | 已完成；价值已转化为 §7 的约束与 §4 的 API |
| 一次性治理/验收的执行快照（删了几行 fake、当时 n_valid 是多少） | 数据会变；只保留**结论**与 §6.3 的基线 |
| 本机 Docker 为主路径的叙述 | 现行是 VPS 运行 |
| L3 页面 / IA / g1geo 排版长文 | 属前端产品，另成文档 |
| Playwright 通用教程、截图技术长文 | 只保留「我们怎么取证」的约束（§7） |
| Git 教程长文 | 运维保留 push 必要命令即可（§10） |
| 架构长文、开源项目评估大表 | 背景材料，非现行规格 |
| 完整建表 DDL 与索引建议 | 代码是真相（`entities.py` / `schema.py`）；文档抄一份必然烂掉 |
| M0–M4 迭代计划、P0–P5 落地顺序 | 已走完或已改道 |
| counts 的 `category` 过滤参数设想 | **已拍板不做**（§4） |
| 把 rate 写进 `metric_snapshots` 当权威 | 与分层冲突（§2.1） |
| 多采样众数代表值、Phase 1.5 采样方案 | 未实现，且与「counts only」分层冲突 |

---

## 13. 维护规则

1. 后端规格**只改这一文件**（将来明确拆分时再拆，禁止再长出 01–27）。  
2. **先改代码与测试，再改本文。** 本文描述现状，不描述愿望。  
3. 写进本文的事实必须**当场对着代码核过**；核不动的写进 §11 而不是当成规格。  
4. 数据快照（如 §6.3 基线）必须带日期，且只保留一份最新的。
