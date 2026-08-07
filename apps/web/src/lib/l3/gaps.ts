/**
 * 覆盖缺口 —— 本品缺席或明显落后、且竞品在场的提问。
 *
 * 这是整个看板唯一数据完全齐备、且输出可直接执行的部分：
 * 结果是一张「该去哪些提问下补内容」的清单。
 */
import { rate } from './rates'

export type GapTier = 'absent' | 'trailing'
export type GapPriority = 'high' | 'mid' | 'low'

export interface BrandHit {
  brandId: number
  /** 命中数；null 与 0 等价（该品牌在这条提问下一次都没出现） */
  m: number | null
}

export interface GapInput {
  promptId: number
  /** 该提问的有效样本数，全行公共分母 */
  n: number
  ownM: number
  competitors: BrandHit[]
}

export interface Gap {
  promptId: number
  n: number
  ownM: number
  tier: GapTier
  /** 命中数 > 0 的竞品，按命中数降序 */
  competitorsPresent: BrandHit[]
  score: number
  priority: GapPriority
}

/** 「明显落后」的判定阈值：本品命中率低于最高竞品的这个比例 */
const TRAILING_RATIO = 0.5

/**
 * 判定一条提问是不是缺口。
 *
 * - `absent`   本品一次都没被提到，但至少一个竞品出现了
 * - `trailing` 本品有命中，但命中率不到最高竞品的一半
 * - `null`     不是缺口
 *
 * 「明显落后」这一档是我们对 GeoMonitor 的扩展 —— 它只定义了完全缺席。
 * 但 1/3 对 3/3 同样是丢单，只做 0 分那一档会漏掉一半的可执行信息。
 */
export function classifyGap(input: GapInput): GapTier | null {
  const present = competitorsPresent(input.competitors)
  if (present.length === 0) return null

  const ownRate = rate(input.ownM, input.n)
  if (ownRate === null) return null
  if (ownRate === 0) return 'absent'

  const bestCompetitorRate = present.reduce((best, c) => {
    const r = rate(c.m ?? 0, input.n)
    return r !== null && r > best ? r : best
  }, 0)
  if (bestCompetitorRate <= 0) return null

  return ownRate < bestCompetitorRate * TRAILING_RATIO ? 'trailing' : null
}

export function competitorsPresent(competitors: BrandHit[]): BrandHit[] {
  return competitors
    .filter((c) => (c.m ?? 0) > 0)
    .sort((a, b) => (b.m ?? 0) - (a.m ?? 0))
}

/**
 * 失分量 = Σ max(0, 竞品命中数 − 本品命中数)。
 *
 * 读作「在这条提问下，竞品合计比本品多拿了多少次提及」。
 *
 * 为什么不是「在场竞品数 × 样本数」（初版就是这么写的，写单测时被逮到）：那个公式把
 * 一个 1/3 的竞品和一个 3/3 的竞品算成一样重，结果「适合跑步新手」
 * （6 个竞品各拿一点，本品 1/3 并不算落后）会盖过「2026年跑步鞋」
 * （本品 0/5，三个竞品各 5/5 全线丢单）。排序和常识相反，公式就是错的。
 *
 * 失分量是纯整数运算，不需要先派生比率 —— 正好贴合「后端只给 counts」。
 */
export function gapScore(ownM: number, competitors: BrandHit[]): number {
  return competitors.reduce((acc, c) => acc + Math.max(0, (c.m ?? 0) - ownM), 0)
}

export function gapPriority(score: number): GapPriority {
  if (score >= 10) return 'high'
  if (score >= 5) return 'mid'
  return 'low'
}

/** 从一组提问里挑出全部缺口，按优先级得分降序 */
export function findGaps(inputs: GapInput[]): Gap[] {
  const gaps: Gap[] = []

  for (const input of inputs) {
    const tier = classifyGap(input)
    if (!tier) continue

    const present = competitorsPresent(input.competitors)
    const score = gapScore(input.ownM, input.competitors)

    gaps.push({
      promptId: input.promptId,
      n: input.n,
      ownM: input.ownM,
      tier,
      competitorsPresent: present,
      score,
      priority: gapPriority(score),
    })
  }

  // 同分时完全缺席排在明显落后前面 —— 0 分比落后更该先处理
  return gaps.sort((a, b) => b.score - a.score || tierWeight(b.tier) - tierWeight(a.tier))
}

function tierWeight(tier: GapTier): number {
  return tier === 'absent' ? 1 : 0
}
