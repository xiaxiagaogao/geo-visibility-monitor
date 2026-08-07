/**
 * 后端契约类型 —— 逐字对应 apps/api/app/schemas/*.py。
 *
 * 本轮还没接 API，但类型先按真实契约定死：
 * fixtures 也用这套类型，接 API 时组件层不用改。
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
  created_at: string
  citations: Citation[]
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

/** 平台在 UI 上的接入状态 —— 无 Provider 时禁止假装可跑。
 *  对应 GET /v1/config/platforms 的 available / implemented（API.md §5） */
export interface PlatformOption {
  id: string
  label: string
  connected: boolean
}
