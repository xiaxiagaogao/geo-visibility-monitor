/**
 * 样本（RawResponse）。字段以 `docs/API.md` §7 为准。
 */
import type { RawResponse, RawResponseSummary } from '../types'
import { apiFetch } from './client'

export interface SampleListResult {
  items: RawResponseSummary[]
  /** 过滤后的全量条数，不受分页影响 —— 翻页器的分母 */
  total: number
}

/**
 * 某次运行的样本列表。
 *
 * **`runId` 是必填的，没有省略它的重载**，同 `fetchRunCounts` ——
 * 不带 run_id 列出来的是这个品牌**历史所有运行**的样本，
 * 而页面上方每一个 KPI 都是「这一次运行」的数。两者并排放着却不同口径，
 * 是那种没人会当场发现、事后也说不清的错。
 *
 * 走的是 `/v1/responses/summary` 而不是 `/v1/responses`：后者每行都拖着
 * 完整 `full_text` 与 `raw_json`，而列表上一个字都不显示它们（API.md §7）。
 *
 * **`limit` 有上限 200，且不该拿满。** 分页是这个页面的正常形态，
 * 不是「先全拉下来再说」的临时方案。
 */
export async function listRunSamples(params: {
  runId: number
  limit?: number
  offset?: number
  /** `ok` | `empty` | `too_short` | `error`；不传 = 全要（含不进分母的） */
  answerStatus?: string
  platform?: string
}): Promise<SampleListResult> {
  return apiFetch<SampleListResult>('/v1/responses/summary', {
    query: {
      run_id: params.runId,
      limit: params.limit,
      offset: params.offset,
      answer_status: params.answerStatus,
      platform: params.platform,
    },
  })
}

/**
 * 单条样本的**全文**，证据页用。
 *
 * 这里就该用 `/v1/responses/{id}` 而不是 summary —— 证据页的全部意义
 * 就是把 L0 原文摆出来。列表用 summary、详情用这个，两者的分工是
 * 「一次拉一条全文」对「一页拉 20 条全文」，不是「新旧两套」。
 *
 * 返回里的 `mentions[].first_offset` / `matched_term` 是高亮的唯一依据，
 * **不许前端自己拿 matched_term 去 indexOf**（API.md §7.1）：
 * 大小写折叠与别名优先级的规则都在后端，前端重造一套就会和 L1 口径分叉，
 * 而这个产品的可信度全建立在「UI 上的数和 L1 标注是同一套」上面。
 */
export async function getResponse(responseId: number): Promise<RawResponse> {
  return apiFetch<RawResponse>(`/v1/responses/${responseId}`)
}
