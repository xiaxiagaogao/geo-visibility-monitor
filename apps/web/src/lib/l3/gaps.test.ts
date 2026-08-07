import { describe, expect, it } from 'vitest'

import { classifyGap, findGaps, gapPriority, gapScore, type GapInput } from './gaps'

const comp = (brandId: number, m: number | null) => ({ brandId, m })

describe('classifyGap', () => {
  it('本品挂零 + 竞品在场 = 完全缺席', () => {
    // 2026年跑步鞋哪个品牌好？ 安踏 0/5，耐克/阿迪/亚瑟士 各 5/5
    const input: GapInput = {
      promptId: 109,
      n: 5,
      ownM: 0,
      competitors: [comp(36, 5), comp(37, 5), comp(41, 5), comp(35, null)],
    }
    expect(classifyGap(input)).toBe('absent')
  })

  it('本品挂零但竞品也全挂零 = 不是缺口', () => {
    // 大家都没被提到，那是这条提问本身没人答品牌，不是我们丢单
    expect(
      classifyGap({ promptId: 1, n: 5, ownM: 0, competitors: [comp(36, 0), comp(37, null)] }),
    ).toBeNull()
  })

  it('本品不到最高竞品一半 = 明显落后', () => {
    // 马拉松：安踏 1/3 = 33.3%，最高竞品 3/3 = 100%，33.3% < 50%
    expect(
      classifyGap({ promptId: 108, n: 3, ownM: 1, competitors: [comp(36, 3), comp(41, 3)] }),
    ).toBe('trailing')
  })

  it('本品过半就不算落后', () => {
    // 2/3 = 66.7% ≥ 100% × 0.5
    expect(
      classifyGap({ promptId: 1, n: 3, ownM: 2, competitors: [comp(36, 3)] }),
    ).toBeNull()
  })

  it('本品领先当然不是缺口', () => {
    expect(
      classifyGap({ promptId: 101, n: 5, ownM: 5, competitors: [comp(35, 5), comp(38, 5)] }),
    ).toBeNull()
  })

  it('无有效样本时不做判断', () => {
    expect(classifyGap({ promptId: 1, n: 0, ownM: 0, competitors: [comp(36, 3)] })).toBeNull()
  })
})

describe('gapScore / gapPriority', () => {
  it('失分量 = 竞品合计比本品多拿的提及次数', () => {
    // 本品 0，三个竞品各 5 → 15
    expect(gapScore(0, [comp(36, 5), comp(37, 5), comp(41, 5)])).toBe(15)
    // 本品 1，三个竞品各 3 → (3-1)×3 = 6
    expect(gapScore(1, [comp(36, 3), comp(37, 3), comp(41, 3)])).toBe(6)
  })

  it('打不过我们的竞品不倒扣分', () => {
    expect(gapScore(3, [comp(36, 1), comp(37, 0), comp(41, null)])).toBe(0)
  })

  it('弱竞品不该把强竞品的信号冲淡', () => {
    // 适合跑步新手：6 个竞品在场，但多数和本品一样只有 1/3
    const crowded = gapScore(1, [
      comp(35, 1),
      comp(36, 3),
      comp(37, 2),
      comp(38, 1),
      comp(39, 1),
      comp(41, 3),
    ])
    // 2026年跑步鞋：只有 3 个竞品，但本品全线挂零
    const wipeout = gapScore(0, [comp(36, 5), comp(37, 5), comp(41, 5)])
    expect(crowded).toBe(5)
    expect(wipeout).toBe(15)
    expect(wipeout).toBeGreaterThan(crowded)
  })

  it('按 ≥10 高 · 5–9 中 · <5 低 分档', () => {
    expect(gapPriority(15)).toBe('high')
    expect(gapPriority(10)).toBe('high')
    expect(gapPriority(9)).toBe('mid')
    expect(gapPriority(5)).toBe('mid')
    expect(gapPriority(4)).toBe('low')
  })
})

describe('findGaps · 对上 docs/29 §3.3 那张表', () => {
  // 安踏监测集真实数据，列序：李宁 耐克 阿迪 特步 361度 鸿星尔克 亚瑟士
  const inputs: GapInput[] = [
    { promptId: 101, n: 5, ownM: 5, competitors: [comp(35, 5), comp(38, 5), comp(39, 5), comp(40, 5)] },
    { promptId: 102, n: 4, ownM: 4, competitors: [comp(35, 4), comp(37, 3), comp(41, 4)] },
    { promptId: 103, n: 3, ownM: 3, competitors: [comp(35, 3), comp(36, 1), comp(38, 3), comp(39, 3)] },
    { promptId: 104, n: 3, ownM: 3, competitors: [comp(35, 3), comp(36, 3), comp(37, 3), comp(39, 3), comp(41, 1)] },
    { promptId: 105, n: 3, ownM: 3, competitors: [comp(35, 3), comp(36, 3), comp(37, 3), comp(38, 2), comp(39, 2), comp(41, 3)] },
    { promptId: 106, n: 3, ownM: 1, competitors: [comp(35, 1), comp(36, 3), comp(37, 2), comp(38, 1), comp(39, 1), comp(41, 3)] },
    { promptId: 107, n: 3, ownM: 1, competitors: [comp(35, 1), comp(39, 3), comp(41, 3)] },
    { promptId: 108, n: 3, ownM: 1, competitors: [comp(36, 3), comp(37, 3), comp(41, 3)] },
    { promptId: 109, n: 5, ownM: 0, competitors: [comp(36, 5), comp(37, 5), comp(41, 5)] },
    { promptId: 110, n: 3, ownM: 0, competitors: [comp(36, 3), comp(37, 1)] },
  ]

  const gaps = findGaps(inputs)

  it('挑出 5 条缺口', () => {
    expect(gaps.map((g) => g.promptId).sort()).toEqual([106, 107, 108, 109, 110])
  })

  it('两条完全缺席就是那两条本品挂零的', () => {
    expect(gaps.filter((g) => g.tier === 'absent').map((g) => g.promptId).sort()).toEqual([
      109, 110,
    ])
  })

  it('五条满分的提问一条都不该进来', () => {
    for (const id of [101, 102, 103, 104, 105]) {
      expect(gaps.some((g) => g.promptId === id), `prompt ${id}`).toBe(false)
    }
  })

  it('2026年跑步鞋是唯一的高优先级 —— 失分量 15', () => {
    const high = gaps.filter((g) => g.priority === 'high')
    expect(high).toHaveLength(1)
    expect(high[0].promptId).toBe(109)
    expect(high[0].score).toBe(15)
  })

  it('全线丢单排在竞争激烈之前', () => {
    // 109 本品 0/5、三个竞品各 5/5   → 15
    // 106 本品 1/3、六个竞品在场但多数也只 1/3 → 5
    expect(gaps[0].promptId).toBe(109)
    expect(gaps.map((g) => g.score)).toEqual([...gaps.map((g) => g.score)].sort((a, b) => b - a))
  })

  it('在场竞品按命中数降序排好，便于直接读出对手是谁', () => {
    const g106 = gaps.find((g) => g.promptId === 106)!
    expect(g106.competitorsPresent.map((c) => c.m)).toEqual([3, 3, 2, 1, 1, 1])
  })
})
