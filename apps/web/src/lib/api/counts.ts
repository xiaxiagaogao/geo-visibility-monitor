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
 * 跨 run 的品牌级累计口径见下面的 `fetchBrandCounts` —— 它**不是**这个函数的
 * 可选参数版本，是另一个函数，理由写在它自己的注释里。
 */
export async function fetchRunCounts(params: {
  brandId: number
  runId: number
  /** 默认 `none`（总览四个数）；矩阵与缺口清单用 `prompt`；分平台面板用 `platform` */
  groupBy?: 'none' | 'day' | 'platform' | 'prompt' | 'search_used'
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

/**
 * **品牌级累计** —— 跨这个品牌的全部 run。
 *
 * 这里原来一个函数都没有，注释写着「等真有那个页面（趋势图）再加，
 * 现在留个口子只会被人顺手调用」。那个页面现在有了：引用榜与联网分桶
 * 问的是「这个品牌整体上被谁引用 / 有多少样本我们不知道联网与否」，
 * 那是**累计问题，不是某一次运行的问题**，硬塞一个 run_id 反而答非所问。
 *
 * ⚠️ **它和 `fetchRunCounts` 刻意是两个函数，不是一个可选参数。**
 * 一个 `runId?: number` 会让「忘了传」和「有意不传」在类型上长得一模一样，
 * 而这两件事的后果差着一个数量级：忘了传，页面上的分母会**静默**变成
 * 该品牌历史全部样本，竞品集也会从快照滑到当前配置。分成两个函数之后，
 * 跨 run 累计只能是**写出来的选择**。
 *
 * ⚠️ **拿它的结果画时间序列之前先想清楚口径。** 它把不同采集条件下的样本
 * 合在一个分母里；要按时间比较，用 `lib/l3/trend` 逐 run 取数并标出断点。
 */
export async function fetchBrandCounts(params: {
  brandId: number
  groupBy?: 'none' | 'day' | 'platform' | 'prompt' | 'search_used'
  platform?: string
}): Promise<CountsResponse> {
  return apiFetch<CountsResponse>('/v1/counts', {
    query: {
      brand_id: params.brandId,
      group_by: params.groupBy,
      platform: params.platform,
    },
  })
}
