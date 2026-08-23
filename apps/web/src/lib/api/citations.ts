/**
 * 引用域名榜 —— `GET /v1/citations/domains`（docs/API.md §4）。
 *
 * 这是这个产品**唯一同行没有的数据**：千问的引用不在页面 DOM 里
 * （页面上那块只有站点图标，一条外链都没有），只存在于 SSE 流里。
 * 公开圈没有第二家从 qianwen.com 抽出过引用（见 docs/CRAWL-INTEL.md）。
 *
 * 这一层不算比率、不排序、不裁剪 —— 派生全在 `lib/l3/citations`。
 */
import type { CitationDomainsResult } from '../types'
import { apiFetch } from './client'

export async function fetchCitationDomains(params: {
  brandId: number
  /** 不传 = 该品牌全部 run 的累计。榜单是累计问题，默认就该是累计 */
  runId?: number
  platform?: string
  /** 后端上限 200。**不传就用后端默认**，别在前端写死另一个数 */
  limit?: number
}): Promise<CitationDomainsResult> {
  return apiFetch<CitationDomainsResult>('/v1/citations/domains', {
    query: {
      brand_id: params.brandId,
      run_id: params.runId,
      platform: params.platform,
      limit: params.limit,
    },
  })
}
