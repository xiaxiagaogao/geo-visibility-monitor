import { describe, expect, it } from 'vitest'

import type { Mention } from '../types'

import { buildHighlights, mentionOrder } from './evidence'

const OWN = 34

/** 正文：安踏在下标 0，耐克在下标 6 */
const TEXT = '安踏和李宁、耐克都是不错的选择。'

const mention = (over: Partial<Mention> & { brand_id: number }): Mention => ({
  id: 1,
  mentioned: true,
  mention_type: 'body',
  position_bucket: 'head',
  position_rank: null,
  evidence_snippet: null,
  first_offset: null,
  matched_term: null,
  ...over,
})

const body = (brandId: number, offset: number, term: string) =>
  mention({ brand_id: brandId, first_offset: offset, matched_term: term })

describe('buildHighlights 不变量自检', () => {
  it('对得上就画', () => {
    const { highlights, mismatches } = buildHighlights(TEXT, [body(OWN, 0, '安踏')], OWN)
    expect(mismatches).toHaveLength(0)
    expect(highlights).toEqual([{ brandId: OWN, offset: 0, matchedTerm: '安踏', own: true }])
  })

  it('offset 是 0 也要画 —— 0 是正文第一个字，不是假值', () => {
    // `if (!m.first_offset) continue` 会把这条吃掉，而首字命中恰恰最常见
    const { highlights } = buildHighlights(TEXT, [body(OWN, 0, '安踏')], OWN)
    expect(highlights).toHaveLength(1)
  })

  it('对不上就不画，进 mismatches', () => {
    // 标注说下标 6 是「李宁」，但那儿实际是「耐克」—— 画上去就是拿错的原文骗人
    const { highlights, mismatches } = buildHighlights(TEXT, [body(35, 6, '李宁')], OWN)
    expect(highlights).toHaveLength(0)
    expect(mismatches).toEqual([{ brandId: 35, offset: 6, expected: '李宁', actual: '耐克' }])
  })

  it('对不上时**不做 indexOf 兜底** —— 正文里真有这个词也不许自己找', () => {
    // 「李宁」在正文里确实存在（下标 3），但标注给的是 6。
    // 兜底找到 3 会让页面看起来完全正常，而 UI 标的已经不是 L1 数的那一处。
    const { highlights, mismatches } = buildHighlights(TEXT, [body(35, 6, '李宁')], OWN)
    expect(highlights).toHaveLength(0)
    expect(mismatches).toHaveLength(1)
  })

  it('offset 越过正文末尾 → actual 是空串，同样只进 mismatches', () => {
    const { highlights, mismatches } = buildHighlights(TEXT, [body(OWN, 9999, '安踏')], OWN)
    expect(highlights).toHaveLength(0)
    expect(mismatches[0].actual).toBe('')
  })

  it('大小写不一致算对不上 —— 后端存的是原文里的表面形式', () => {
    // match_brand 返回折叠后的 'nike'，落库存的是原文的 'Nike'。
    // 真出现 'nike' 说明这条没走 surface_term，是标注侧的 bug，要暴露不要美化
    const text = '国际品牌里 Nike 依然强势。'
    const { highlights, mismatches } = buildHighlights(text, [body(36, 6, 'nike')], OWN)
    expect(highlights).toHaveLength(0)
    expect(mismatches[0]).toMatchObject({ expected: 'nike', actual: 'Nike' })
  })
})

describe('buildHighlights 与 emoji —— offset 是码点不是 UTF-16 单元', () => {
  // 部署后冒烟在生产数据上抓到的真实 bug：响应 73 有 4 个 emoji，
  // 810 码点 / 814 UTF-16 单元，于是 JS 的 slice 把 'Nike' 切成了 '如Nik'。
  // 两边都没错，是跨语言的索引口径没对齐。

  it('正文含 emoji 时仍能对上 —— 这是回归用例', () => {
    // 🏃 在 Python 里算 1 个码点，在 JS 里算 2 个 UTF-16 单元
    const text = '跑步🏃推荐安踏和耐克。'
    // 按码点数：跑(0)步(1)🏃(2)推(3)荐(4)安(5)踏(6)
    const { highlights, mismatches } = buildHighlights(text, [body(OWN, 5, '安踏')], OWN)
    expect(mismatches).toHaveLength(0)
    expect(highlights).toHaveLength(1)
  })

  it('多个 emoji 累积错位也要能对上', () => {
    const text = '🏋️🤸🏃💡安踏'
    // ZWJ / 变体选择符也各算一个码点 —— 所以不能靠数「几个 emoji」推 offset，
    // 只能按 Array.from 的结果数
    const offset = Array.from(text).indexOf('安')
    const { highlights, mismatches } = buildHighlights(text, [body(OWN, offset, '安踏')], OWN)
    expect(mismatches).toHaveLength(0)
    expect(highlights[0].offset).toBe(offset)
  })

  it('用 UTF-16 单元当 offset 会被判成对不上 —— 不许静默放行', () => {
    // 如果哪天有人把后端改成落 UTF-16 偏移而没同步前端，这条会红
    const text = '跑步🏃推荐安踏'
    const utf16Offset = text.indexOf('安踏') // 6，比码点索引 5 多 1
    const { highlights, mismatches } = buildHighlights(text, [body(OWN, utf16Offset, '安踏')], OWN)
    expect(highlights).toHaveLength(0)
    expect(mismatches).toHaveLength(1)
  })
})

describe('buildHighlights 哪些该跳过（不是错误）', () => {
  it('没被提及的品牌跳过', () => {
    const m = mention({ brand_id: 41, mentioned: false, mention_type: 'none' })
    const { highlights, mismatches } = buildHighlights(TEXT, [m], OWN)
    expect(highlights).toHaveLength(0)
    expect(mismatches).toHaveLength(0)
  })

  it('citation_only 跳过 —— 正文里没出现，没有位置可标', () => {
    // 它不是「标注错了」，是「命中在引用里」。混进 mismatches 会把
    // 一个正常结论报成数据异常
    const m = mention({
      brand_id: 41,
      mention_type: 'citation_only',
      position_bucket: null,
      first_offset: null,
      matched_term: null,
    })
    const { highlights, mismatches } = buildHighlights(TEXT, [m], OWN)
    expect(highlights).toHaveLength(0)
    expect(mismatches).toHaveLength(0)
  })

  it('只有 offset 没有 matched_term 也跳过，不当成 0 长度命中', () => {
    const m = mention({ brand_id: 41, first_offset: 3, matched_term: null })
    expect(buildHighlights(TEXT, [m], OWN).highlights).toHaveLength(0)
  })
})

describe('buildHighlights 排序与本品标记', () => {
  it('按 offset 升序，不跟随入参顺序', () => {
    const { highlights } = buildHighlights(
      TEXT,
      [body(36, 6, '耐克'), body(OWN, 0, '安踏'), body(35, 3, '李宁')],
      OWN,
    )
    expect(highlights.map((h) => h.offset)).toEqual([0, 3, 6])
  })

  it('own 按 brand_id 判，不按顺序', () => {
    const { highlights } = buildHighlights(
      TEXT,
      [body(36, 6, '耐克'), body(OWN, 0, '安踏')],
      OWN,
    )
    expect(highlights.find((h) => h.brandId === OWN)?.own).toBe(true)
    expect(highlights.find((h) => h.brandId === 36)?.own).toBe(false)
  })

  it('同一个 offset 上本品排在前面', () => {
    // 别名重叠可能撞同一个 offset；渲染时只取第一个，
    // 本品被竞品盖掉是最难跟客户解释的那种错
    const { highlights } = buildHighlights('安踏', [body(36, 0, '安踏'), body(OWN, 0, '安踏')], OWN)
    expect(highlights[0].brandId).toBe(OWN)
  })
})

describe('mentionOrder', () => {
  it('给出「谁先被提到」的品牌顺序，去重', () => {
    const { highlights } = buildHighlights(
      TEXT,
      [body(36, 6, '耐克'), body(OWN, 0, '安踏'), body(35, 3, '李宁')],
      OWN,
    )
    expect(mentionOrder(highlights)).toEqual([OWN, 35, 36])
  })

  it('没有正文命中时是空数组', () => {
    expect(mentionOrder([])).toEqual([])
  })
})
