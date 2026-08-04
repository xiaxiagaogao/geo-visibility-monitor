/**
 * 派生视图数据 —— 页面组件只负责摆位置，算什么摆什么在这里定。
 *
 * 接 API 之后这一层不用动：入参换成 CountsResponse 即可，
 * 因为 fixtures 的形状本来就是照着 counts 契约定的。
 */
import type { BarDatum } from '@/components/charts/EmphasisBars'

import { BRAND_NAMES, MATRIX, OWN_BRAND_ID, PROMPT_BY_ID, TOTALS } from './fixtures'
import { rate } from './l3/rates'

/** 本品在每条提问下的命中情况，按提及率降序（挂零的沉到底部，最扎眼） */
export function ownRateByPrompt(): BarDatum[] {
  return MATRIX.map((row) => {
    const m = row.cells.find((c) => c.brandId === OWN_BRAND_ID)?.m ?? 0
    return {
      key: row.promptId,
      label: PROMPT_BY_ID.get(row.promptId)?.text ?? `#${row.promptId}`,
      m,
      n: row.n,
      own: true,
    }
  }).sort((a, b) => {
    const ra = rate(a.m, a.n) ?? -1
    const rb = rate(b.m, b.n) ?? -1
    return rb - ra || b.n - a.n
  })
}

/** 本品 vs 竞品的整体提及对比，按提及率降序 —— 本品高亮，其余灰 */
export function brandComparison(): BarDatum[] {
  const rows: BarDatum[] = [
    {
      key: OWN_BRAND_ID,
      label: BRAND_NAMES[OWN_BRAND_ID],
      m: TOTALS.brand.mMentioned,
      n: TOTALS.nValid,
      own: true,
    },
    ...TOTALS.competitors.map((c) => ({
      key: c.brandId,
      label: BRAND_NAMES[c.brandId] ?? `#${c.brandId}`,
      m: c.mMentioned,
      n: TOTALS.nValid,
    })),
  ]
  return rows.sort((a, b) => b.m - a.m)
}

/** 本品一次都没被提到的提问数 —— 双峰结论的入口 */
export function zeroHitPromptCount(): number {
  return MATRIX.filter((row) => (row.cells.find((c) => c.brandId === OWN_BRAND_ID)?.m ?? 0) === 0)
    .length
}

/** 满分提问数 */
export function fullHitPromptCount(): number {
  return MATRIX.filter((row) => {
    const m = row.cells.find((c) => c.brandId === OWN_BRAND_ID)?.m ?? 0
    return m === row.n
  }).length
}

/** SoV 的分母：本品 + 全部竞品的命中总数 */
export function sovDenominator(): number {
  return TOTALS.competitors.reduce((acc, c) => acc + c.mMentioned, TOTALS.brand.mMentioned)
}
