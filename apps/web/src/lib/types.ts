/**
 * 后端契约类型 —— 逐字对应 apps/api/app/schemas/*.py。
 *
 * 与品牌数量无关，IA 重构后继续可用。
 * （原来还有一份 fixtures 共用这套类型，已随单品牌页面删除。）
 */

/** apps/api/app/schemas/counts.py :: DenominatorCounts */
export interface DenominatorCounts {
  definition: string
  n_valid: number
  n_total_responses: number
  n_empty: number
  n_too_short: number
  n_error: number
  n_unannotated: number
}

/** apps/api/app/schemas/counts.py :: BrandMentionCounts */
export interface BrandMentionCounts {
  brand_id: number
  m_mentioned: number
  m_body: number
  m_citation_only: number
  m_none: number
  m_head: number
  m_middle: number
  m_tail: number
  /**
   * `position_rank == 1` 的样本数 —— 首位提及率的分子。
   *
   * **可选是刻意的，不是偷懒。** 开发期 `next.config.ts` 的 rewrites 把取数
   * 代理到线上，所以本机跑的前端吃的是**已部署**的后端 —— 这个字段是新加的，
   * 后端没上线之前它就是 `undefined`。声明成必填只会让类型撒谎，
   * 页面照样拿到 undefined，然后 `undefined / 21` 算出 `NaN%` 显示出去。
   *
   * 拿不到时该走降级态，不是当 0 —— `0/21 = 0.0%` 是「一次都没排第一」，
   * 而真相是「这个数还取不到」，两者是完全不同的结论。
   */
  m_first?: number
}

/**
 * apps/api/app/schemas/counts.py :: CountsBucket
 *
 * ⚠️ group_by=prompt 时 `key` 是 **prompt_id 的字符串**，不是提问文案
 * （apps/api/app/services/counts.py:170）。行标题要靠 /v1/prompts 关联。
 */
export interface CountsBucket {
  key: string
  denominator: DenominatorCounts
  brand: BrandMentionCounts
  competitors: BrandMentionCounts[]
}

/** apps/api/app/schemas/counts.py :: CountsResponse */
export interface CountsResponse {
  brand_id: number
  filters: Record<string, unknown>
  group_by: 'none' | 'day' | 'platform' | 'prompt'
  denominator: DenominatorCounts
  brand: BrandMentionCounts
  competitors: BrandMentionCounts[]
  series: CountsBucket[]
  note: string
}

/** apps/api/app/schemas/brand.py :: BrandOut */
export interface Brand {
  id: number
  workspace_id: number
  name: string
  name_en: string | null
  industry: string | null
  aliases: string[]
  /** 竞品**列顺序的唯一依据** —— 不许拿 counts.competitors 的数组下标当顺序 */
  competitor_ids: number[]
  created_at: string
}

/** apps/api/app/schemas/prompt.py :: PromptOut */
export interface Prompt {
  id: number
  brand_id: number
  text: string
  category: string | null
  tags: unknown[]
  is_active: boolean
  created_at: string
}

/** apps/api/app/schemas/crawl.py :: MentionOut */
export interface Mention {
  id: number
  brand_id: number
  mentioned: boolean
  mention_type: string
  position_bucket: 'head' | 'middle' | 'tail' | null
  position_rank: number | null
  evidence_snippet: string | null
  /**
   * 首次命中在 `full_text` 里的字符下标。`citation_only` 时为 null（正文没出现）。
   *
   * 和 `matched_term` 一起满足一条**可自检的不变量**（API.md §7.1）：
   * `full_text.slice(first_offset, first_offset + matched_term.length) === matched_term`
   * 后端在全库 179 条命中上验过 179/179。前端 assert 它，错位会立刻暴露。
   */
  first_offset: number | null
  /** 实际命中的别名（保留原文大小写）—— 用于展示「靠哪个别名命中的」 */
  matched_term: string | null
}

/** apps/api/app/schemas/crawl.py :: CitationOut */
export interface Citation {
  id: number
  cite_index: number | null
  url: string
  domain: string
  title: string | null
  snippet: string | null
}

/** apps/api/app/schemas/crawl.py :: RawResponseOut */
export interface RawResponse {
  id: number
  job_id: number
  platform: string
  prompt_text: string
  full_text: string
  html_path: string | null
  screenshot_path: string | null
  raw_json: Record<string, unknown> | null
  latency_ms: number | null
  answer_status: string | null
  annotator_version: string | null
  /**
   * P2-37 联网标注。**三态，`null` 不是 `false`**：
   * `true`=联网了 · `false`=**确认**没联网 · `null`=我们不知道
   * （P2-37 上线前的样本、别的平台、解析失败）。
   * 展示口径统一走 `lib/l3/search-used.ts`，别在组件里自己判。
   */
  search_used: boolean | null
  created_at: string
  citations: Citation[]
  mentions: Mention[]
}

/**
 * apps/api/app/schemas/crawl.py :: RawResponseSummaryOut
 *
 * 列表用的轻量投影（`GET /v1/responses/summary`）。
 *
 * **这里没有 `full_text` 和 `raw_json`，而且是故意在类型上就没有。**
 * 后端也没把它们做成可选字段：「有时有有时没有」的字段会让类型撒谎，
 * 拿到 undefined 时页面不报错、只渲染空白。要全文去 `GET /v1/responses/{id}`。
 *
 * `text_length > text_preview.length` 就是「这条被截断了」的判据 ——
 * 别去数 preview 的字数（后端按字符截，前端数出来的是 UTF-16 code unit）。
 */
export interface RawResponseSummary {
  id: number
  job_id: number
  platform: string
  prompt_text: string
  /** 正文前 160 字 */
  text_preview: string
  /** 正文总字数 */
  text_length: number
  screenshot_path: string | null
  latency_ms: number | null
  answer_status: string | null
  /** 为 null 表示这条**还没跑过 L1 标注** —— 和「标注过但没提及」是两回事 */
  annotator_version: string | null
  /** P2-37 三态，语义同 `RawResponse.search_used`（`null` ≠ `false`） */
  search_used: boolean | null
  created_at: string
  mentions: Mention[]
}

/** apps/api/app/schemas/crawl.py :: CrawlJobOut */
export interface CrawlJob {
  id: number
  prompt_id: number
  platform: string
  status: 'pending' | 'running' | 'success' | 'failed'
  sample_index: number
  error_message: string | null
  started_at: string | null
  finished_at: string | null
  created_at: string
  response_id: number | null
}

/**
 * `GET /v1/config/platforms` 的一项。**别硬编码平台清单**（API.md §5）——
 * 接第二个平台时后端改一行，前端零改动。
 *
 * `available` 与 `implemented` 是**两个字段**，不要合并：
 *   · `available`   现在建任务能不能跑完 → 决定 chip 可点还是灰显
 *   · `implemented` 有没有 real Provider → 区分「没接」和「在跑假数据」
 * 合成一个 boolean 就分不出「豆包没接」和「fake 模式下 deepseek 在产假数据」。
 */
export interface PlatformOption {
  code: string
  label: string
  available: boolean
  implemented: boolean
  note: string | null
}

/** `GET /v1/config/platforms` 的响应 */
export interface PlatformsConfig {
  /** `real` | `fake` —— fake 时产出的是假数据，界面要说明白 */
  crawl_mode: string
  items: PlatformOption[]
}

/** `apps/api/app/schemas/task.py :: TaskOut` */
export interface Task {
  id: number
  brand_id: number
  name: string
  platforms: string[]
  samples: number
  is_active: boolean
  created_at: string
  /** 列表页直接用，不必逐行再打一次 runs 接口 */
  latest_run_id: number | null
  latest_run_at: string | null
  /** `empty` | `pending` | `running` | `success` | `partial` | `failed` */
  latest_run_status: RunStatus | null
}

/**
 * run 状态。**`partial` 是独立一档，不能当 success 显示** ——
 * 部分成功意味着分母少了一截，所有比率会静默偏高。
 */
export type RunStatus = 'empty' | 'pending' | 'running' | 'success' | 'partial' | 'failed'

/**
 * `apps/api/app/schemas/task.py :: RunOut`
 *
 * `status` 是**每次请求现算的**（`derive_run_status`），runs 表里没有这一列 ——
 * 所以拿到手的 run 对象不能长期缓存当真值，跑着的 run 要重取才会变。
 */
export interface Run {
  id: number
  task_id: number
  platforms: string[]
  note: string | null
  created_at: string
  status: RunStatus
  n_jobs: number
}

/**
 * `apps/api/app/schemas/task.py :: RunPromptOut`
 *
 * **快照，不是实时查的。** 带 `prompt_text` 是因为提问词正文可改 ——
 * 有它就不必再打 `/v1/prompts` 关联行标题，也不会被后来的改名改写历史。
 */
export interface RunPrompt {
  prompt_id: number
  prompt_text: string
}

/**
 * `apps/api/app/schemas/task.py :: RunCompetitorOut`
 *
 * 带 `brand_name` 同理：竞品被删之后，「当时拿它比过」这个事实仍应留着。
 */
export interface RunCompetitor {
  competitor_brand_id: number
  brand_name: string
}

/** `apps/api/app/schemas/task.py :: RunDetailOut` = RunOut + 两份快照 */
export interface RunDetail extends Run {
  prompts: RunPrompt[]
  competitors: RunCompetitor[]
}

/**
 * 图表视图模型 —— 一根 emphasis 横条要的全部数据。
 *
 * 原来定义在 `lib/selectors.ts`（已随单品牌页面删除），挪到这里：
 * 它与品牌数量无关，`own` 只标记「这一根是本品」，谁是本品由调用方决定。
 *
 * **同时带 m 和 n 是刻意的**：凡显示比率必须同时显示 m / n（API.md §4.2 第 4 条），
 * 只传一个算好的 rate 进来，这条纪律在类型层面就守不住了。
 */
export interface BarDatum {
  key: string | number
  label: string
  m: number
  n: number
  own?: boolean
}
