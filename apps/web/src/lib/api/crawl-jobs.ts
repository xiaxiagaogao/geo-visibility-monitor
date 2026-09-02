/**
 * 采样任务（CrawlJob）。字段以 `docs/API.md` §8 为准。
 */
import { apiFetch } from './client'

import type { CrawlJob } from '@/lib/types'

interface CrawlJobCountResult {
  items: unknown[]
  total: number
}

interface CrawlJobListResult {
  items: CrawlJob[]
  total: number
}

/**
 * 某次运行里某种状态的采样条数。
 *
 * **只返回 total，不返回 items** —— 页面要的就是一个数字，
 * 而这个端点每行都带 job 详情。`limit: 1` 让服务端只回一行，
 * `total` 仍是过滤后的全量。
 *
 * 存在的理由：**失败的 job 不产出 `RawResponse`**，所以「这次运行还有
 * 几条没回来」在 `/v1/responses` 里根本数不出来 —— 样本表下面那行
 * 「另有 N 条没回来」只能从这里取。partial 状态的 run 上，
 * 这个数就是分母少掉的那一截。
 */
export async function countRunJobs(params: {
  runId: number
  /** `pending` | `running` | `success` | `failed`；不传 = 这次运行的全部采样 */
  status?: string
}): Promise<number> {
  const res = await apiFetch<CrawlJobCountResult>('/v1/crawl-jobs', {
    query: { run_id: params.runId, status: params.status, limit: 1 },
  })
  return res.total
}

/**
 * 这次运行**失败的那些采样**，要 items 不只要 total。
 *
 * 和 `countRunJobs` 分成两个函数而不是加一个可选参数 —— 和
 * `fetchBrandCounts` / `fetchRunCounts` 同一条理由：「只要个数」和
 * 「要逐条看原因」是两个不同的问题，让调用点自己说清要哪个。
 *
 * `limit` 有上限是刻意的：这一层只服务「失败原因分布」那一句话，
 * 不是一个可翻页的失败清单。真要逐条排查是 `/qa` 的事。
 */
export async function listFailedJobs(params: {
  runId: number
  limit?: number
}): Promise<CrawlJob[]> {
  const res = await apiFetch<CrawlJobListResult>('/v1/crawl-jobs', {
    query: { run_id: params.runId, status: 'failed', limit: params.limit ?? 200 },
  })
  return res.items
}
