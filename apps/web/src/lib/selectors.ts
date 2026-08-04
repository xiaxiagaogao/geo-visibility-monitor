/**
 * 派生视图数据 —— 页面组件只负责摆位置，算什么、摆什么在这里定。
 *
 * 接 API 之后这一层不用动：入参换成 CountsResponse 即可，
 * 因为 fixtures 的形状本来就是照着 counts 契约定的。
 */
import { BRAND_NAMES, MATRIX, OWN_BRAND_ID, PROMPT_BY_ID, TOTALS } from './fixtures'
import { findGaps, type Gap, type GapInput } from './l3/gaps'
import { rate } from './l3/rates'

export interface BarDatum {
  key: string | number
  label: string
  m: number
  n: number
  own?: boolean
}

/** 本品在每条提问下的命中情况，按提及率降序 —— 挂零的沉到底部，最扎眼 */
export function ownRateByPrompt(): BarDatum[] {
  return MATRIX.map((row) => ({
    key: row.promptId,
    label: PROMPT_BY_ID.get(row.promptId)?.text ?? `#${row.promptId}`,
    m: ownHits(row.promptId),
    n: row.n,
    own: true,
  })).sort((a, b) => {
    const ra = rate(a.m, a.n) ?? -1
    const rb = rate(b.m, b.n) ?? -1
    return rb - ra || b.n - a.n
  })
}

/** 本品 vs 竞品的整体提及对比，按命中数降序 —— 本品高亮，其余灰 */
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

export function ownHits(promptId: number): number {
  const row = MATRIX.find((r) => r.promptId === promptId)
  return row?.cells.find((c) => c.brandId === OWN_BRAND_ID)?.m ?? 0
}

/** 覆盖缺口清单，已按失分量降序 */
export function gapList(): Gap[] {
  const inputs: GapInput[] = MATRIX.map((row) => ({
    promptId: row.promptId,
    n: row.n,
    ownM: ownHits(row.promptId),
    competitors: row.cells
      .filter((c) => c.brandId !== OWN_BRAND_ID)
      .map((c) => ({ brandId: c.brandId, m: c.m })),
  }))
  return findGaps(inputs)
}

export function promptText(promptId: number): string {
  return PROMPT_BY_ID.get(promptId)?.text ?? `#${promptId}`
}

export function brandName(brandId: number): string {
  return BRAND_NAMES[brandId] ?? `#${brandId}`
}

/** 满分提问数 —— 用于「60% 是两极平均出来的」那句副文案 */
export function fullHitPromptCount(): number {
  return MATRIX.filter((row) => ownHits(row.promptId) === row.n).length
}

export function zeroHitPromptCount(): number {
  return MATRIX.filter((row) => ownHits(row.promptId) === 0).length
}
