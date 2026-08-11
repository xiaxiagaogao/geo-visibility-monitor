import { describe, expect, it } from 'vitest'

import type { BrandMentionCounts, CountsBucket, RunCompetitor, RunPrompt } from '../types'

import { buildCell, buildMatrix, gapInputsFromMatrix } from './matrix'

const OWN = 34

const prompt = (id: number, text: string): RunPrompt => ({ prompt_id: id, prompt_text: text })
const rival = (id: number, name: string): RunCompetitor => ({
  competitor_brand_id: id,
  brand_name: name,
})

const counts = (brandId: number, m: number): BrandMentionCounts => ({
  brand_id: brandId,
  m_mentioned: m,
  m_body: m,
  m_citation_only: 0,
  m_none: 0,
  m_head: 0,
  m_middle: 0,
  m_tail: 0,
})

/** 一个 group_by=prompt 的桶。key 是 **prompt_id 的字符串** */
const bucket = (
  promptId: number,
  nValid: number,
  ownM: number,
  competitors: BrandMentionCounts[] = [],
): CountsBucket => ({
  key: String(promptId),
  denominator: {
    definition: 'answer_status=ok',
    n_valid: nValid,
    n_total_responses: nValid,
    n_empty: 0,
    n_too_short: 0,
    n_error: 0,
    n_unannotated: 0,
  },
  brand: counts(OWN, ownM),
  competitors,
})

describe('buildCell 四态', () => {
  it('有命中 = hit，带色阶档位', () => {
    expect(buildCell(OWN, 3, 3, true)).toMatchObject({ kind: 'hit', level: 'l3', rate: 1 })
    expect(buildCell(OWN, 1, 3, true)).toMatchObject({ kind: 'hit', level: 'l1' })
    expect(buildCell(OWN, 2, 3, true)).toMatchObject({ kind: 'hit', level: 'l2' })
  })

  it('竞品挂零 = zero', () => {
    expect(buildCell(36, 0, 5, false)).toMatchObject({ kind: 'zero', m: 0, n: 5, rate: 0 })
  })

  it('本品挂零 = zeroOwn —— 和竞品挂零不是同一个样式', () => {
    // 本品缺席是这个产品的核心结论，染成和「某个竞品没出现」一样等于把它藏了
    expect(buildCell(OWN, 0, 5, true).kind).toBe('zeroOwn')
    expect(buildCell(36, 0, 5, false).kind).toBe('zero')
  })

  it('n = 0 = na，rate 是 null 不是 0', () => {
    // 「这条提问这次一条有效样本都没有」≠「跑了但一次没被提到」
    const cell = buildCell(OWN, 0, 0, true)
    expect(cell.kind).toBe('na')
    expect(cell.rate).toBeNull()
  })

  it('本品 n = 0 走 na，不走 zeroOwn —— 不可算不许染成挂零', () => {
    // 这是最容易错的一格：own && m===0 的判断若排在 rate===null 前面，
    // 「没跑出样本」会被画成「本品缺席」，等于凭空造一个红色结论
    expect(buildCell(OWN, 0, 0, true).kind).toBe('na')
  })
})

describe('buildMatrix', () => {
  const prompts = [prompt(101, '国产运动鞋推荐'), prompt(109, '2026年跑步鞋哪个品牌好')]
  const competitors = [rival(36, '耐克'), rival(41, '亚瑟士')]

  it('行序跟随 run 快照，不跟随 series', () => {
    // series 按 key 字符串排序，"101" < "109" 碰巧同序；换成 "9" vs "10"
    // 就会反过来。行序必须由快照定，不能靠 series 的巧合。
    const rows = buildMatrix({
      ownBrandId: OWN,
      prompts,
      competitors,
      series: [bucket(109, 5, 0), bucket(101, 5, 5)],
    })
    expect(rows.map((r) => r.promptId)).toEqual([101, 109])
  })

  it('行标题取自快照的 prompt_text', () => {
    const rows = buildMatrix({ ownBrandId: OWN, prompts, competitors, series: [] })
    expect(rows[0].promptText).toBe('国产运动鞋推荐')
  })

  it('跑空的提问仍然占一行，显示不可算 —— 不许静默消失', () => {
    // 拿 series 当行源的话这一行会没了：用户看到 1 行以为只跑了 1 条提问，
    // 实际是 2 条、有 1 条全挂。那是在隐瞒失败。
    const rows = buildMatrix({
      ownBrandId: OWN,
      prompts,
      competitors,
      series: [bucket(101, 5, 5, [counts(36, 2), counts(41, 1)])],
    })
    expect(rows).toHaveLength(2)
    expect(rows[1].n).toBe(0)
    expect(rows[1].ownRate).toBeNull()
    expect(rows[1].cells.every((c) => c.kind === 'na')).toBe(true)
  })

  it('竞品按 brand_id 关联，不按数组下标', () => {
    // series 里竞品顺序和快照顺序相反 —— 按下标取会把耐克的数记到亚瑟士头上，
    // 而矩阵每一格都还是有值的，界面上完全看不出来
    const rows = buildMatrix({
      ownBrandId: OWN,
      prompts,
      competitors,
      series: [bucket(101, 5, 5, [counts(41, 1), counts(36, 4)])],
    })
    const [own, nike, asics] = rows[0].cells
    expect(own).toMatchObject({ brandId: OWN, m: 5 })
    expect(nike).toMatchObject({ brandId: 36, m: 4 })
    expect(asics).toMatchObject({ brandId: 41, m: 1 })
  })

  it('快照里的竞品在 counts 里没出现时按 0 命中处理', () => {
    // 该竞品这次一条都没被提到，后端可能整个不返回它 —— 这是真的 0，不是不可算
    const rows = buildMatrix({
      ownBrandId: OWN,
      prompts,
      competitors,
      series: [bucket(101, 5, 5, [counts(36, 4)])],
    })
    expect(rows[0].cells[2]).toMatchObject({ brandId: 41, m: 0, kind: 'zero' })
  })

  it('列数 = 本品 + 快照竞品数，第 0 列永远是本品', () => {
    const rows = buildMatrix({ ownBrandId: OWN, prompts, competitors, series: [] })
    expect(rows[0].cells).toHaveLength(3)
    expect(rows[0].cells[0].brandId).toBe(OWN)
  })

  it('没有竞品的品牌也能出矩阵，只有本品一列', () => {
    const rows = buildMatrix({
      ownBrandId: OWN,
      prompts,
      competitors: [],
      series: [bucket(101, 5, 5)],
    })
    expect(rows[0].cells).toHaveLength(1)
  })
})

describe('gapInputsFromMatrix', () => {
  const prompts = [prompt(101, '国产运动鞋推荐'), prompt(109, '2026年跑步鞋哪个品牌好')]
  const competitors = [rival(36, '耐克'), rival(41, '亚瑟士')]

  it('本品只进 ownM，不混进竞品列表', () => {
    const rows = buildMatrix({
      ownBrandId: OWN,
      prompts,
      competitors,
      series: [bucket(101, 5, 5, [counts(36, 2), counts(41, 1)])],
    })
    const [first] = gapInputsFromMatrix(rows)
    expect(first).toEqual({
      promptId: 101,
      n: 5,
      ownM: 5,
      competitors: [
        { brandId: 36, m: 2 },
        { brandId: 41, m: 1 },
      ],
    })
  })

  it('丢掉 n = 0 的行 —— 分母为 0 判不了缺口', () => {
    const rows = buildMatrix({
      ownBrandId: OWN,
      prompts,
      competitors,
      series: [bucket(101, 5, 5)],
    })
    expect(gapInputsFromMatrix(rows).map((g) => g.promptId)).toEqual([101])
  })
})
