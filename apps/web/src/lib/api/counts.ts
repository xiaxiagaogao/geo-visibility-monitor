/**
 * 计数接口 —— 前端算比率的唯一数据源。字段以 `docs/API.md` §4 为准。
 *
 * **后端永远只给整数，永远不返回比率**，除法在 `lib/l3`。这一层不许算。
 */
import type { CountsResponse } from '../types'
import { apiFetch } from './client'

/**
 * 某次运行的计数。
 *
 * **`runId` 是必填的，没有省略它的重载** —— 这是「counts 必须带 run_id」
 * 这条纪律的类型层面守卫，同 `<KpiRate>` 只收 `m`/`n` 的做法。
 *
 * 不带 `run_id` 会同时错两处，而且都不报错、只是数字悄悄不对：
 *   1. 分母变成该品牌**历史全部** run 混算，不是这一次
 *   2. 竞品集取**当前**配置而不是该 run 的快照 —— 别人加个竞品，
 *      你昨天看过的缺口清单今天就变了
 *
 * 跨 run 的品牌级累计口径**故意没有导出函数**。等真有那个页面（趋势图，
 * README §5 明确排在「明确不做」里）再加，现在留个口子只会被人顺手调用。
 */
export async function fetchRunCounts(params: {
  brandId: number
  runId: number
  /** 默认 `none`（总览四个数）；矩阵与缺口清单用 `prompt` */
  groupBy?: 'none' | 'day' | 'platform' | 'prompt'
}): Promise<CountsResponse> {
  return apiFetch<CountsResponse>('/v1/counts', {
    query: {
      brand_id: params.brandId,
      run_id: params.runId,
      group_by: params.groupBy,
    },
  })
}
