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
  /** 默认 `none`（总览四个数）；矩阵与缺口清单用 `prompt`；分平台面板用 `platform` */
  groupBy?: 'none' | 'day' | 'platform' | 'prompt'
  /**
   * 只看某一个平台（P2-09）。**命中矩阵强制单平台就靠它**（PHASE2 §4.0 第 3 条）。
   *
   * 后端一直支持这个参数（`api/counts.py`），**但前端在 P2-09 之前一次都没传过** ——
   * 于是勾了两个平台的任务，KPI 与命中矩阵会**静默混算**：
   * 两个平台表现完全没变，其中一个挂掉一半就能让总数从 50% 涨到 60%。
   *
   * **缺口清单刻意不传它** —— §4.0 第 4 条要求它跨平台合计，
   * 理由是「补内容这个动作是平台无关的」，而且合计之后样本翻倍、判级更稳。
   */
  platform?: string
}): Promise<CountsResponse> {
  return apiFetch<CountsResponse>('/v1/counts', {
    query: {
      brand_id: params.brandId,
      run_id: params.runId,
      group_by: params.groupBy,
      platform: params.platform,
    },
  })
}
