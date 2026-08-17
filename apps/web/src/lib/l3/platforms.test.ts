import { describe, expect, it } from 'vitest'

import type { BrandMentionCounts, CountsBucket, CountsResponse, PlatformOption } from '../types'

import { denominatorParts, platformBars, platformSlices } from './platforms'

/** 造一份 BrandMentionCounts，只填测试关心的三个数。 */
function brand(m_mentioned: number, m_first = 0, brand_id = 34): BrandMentionCounts {
  return {
    brand_id,
    m_mentioned,
    m_body: m_mentioned,
    m_citation_only: 0,
    m_none: 0,
    m_head: 0,
    m_middle: 0,
    m_tail: 0,
    m_first,
  }
}

function bucket(key: string, n_valid: number, m: number, f = 0): CountsBucket {
  return {
    key,
    denominator: {
      definition: 'answer_status=ok',
      n_valid,
      n_total_responses: n_valid,
      n_empty: 0,
      n_too_short: 0,
      n_error: 0,
      n_unannotated: 0,
    },
    brand: brand(m, f),
    competitors: [],
  }
}

function counts(series: CountsBucket[]): CountsResponse {
  const n = series.reduce((a, b) => a + b.denominator.n_valid, 0)
  const m = series.reduce((a, b) => a + b.brand.m_mentioned, 0)
  return {
    brand_id: 34,
    filters: {},
    group_by: 'platform',
    denominator: {
      definition: 'answer_status=ok',
      n_valid: n,
      n_total_responses: n,
      n_empty: 0,
      n_too_short: 0,
      n_error: 0,
      n_unannotated: 0,
    },
    brand: brand(m),
    competitors: [],
    series,
    note: '',
  }
}

const OPTIONS: PlatformOption[] = [
  { code: 'deepseek', label: 'DeepSeek', available: true, implemented: true, note: null },
  { code: 'doubao', label: '豆包', available: true, implemented: true, note: null },
  { code: 'tongyi', label: '通义千问', available: true, implemented: true, note: null },
  { code: 'kimi', label: 'Kimi', available: false, implemented: false, note: 'Provider 未实现' },
]

describe('platformSlices', () => {
  it('把 series 的 key 翻成平台标签', () => {
    const s = platformSlices(counts([bucket('deepseek', 30, 18), bucket('tongyi', 5, 4)]), OPTIONS)

    expect(s.map((x) => x.label)).toEqual(['DeepSeek', '通义千问'])
    expect(s.map((x) => x.nValid)).toEqual([30, 5])
    expect(s.map((x) => x.mMentioned)).toEqual([18, 4])
  })

  it('顺序跟 /v1/config/platforms，不跟 series 的返回顺序', () => {
    // **不许拿 series 数组下标当顺序** —— 后端不保证它稳定，
    // 而顺序一跳，用户会以为数据变了。同 `Brand.competitor_ids` 那条纪律。
    const s = platformSlices(counts([bucket('tongyi', 5, 4), bucket('deepseek', 30, 18)]), OPTIONS)

    expect(s.map((x) => x.code)).toEqual(['deepseek', 'tongyi'])
  })

  it('认不出来的平台代码保留原样，不丢数据', () => {
    // 后端加了平台而前端配置还没刷新时，宁可显示 `kimi2` 也不能把这段样本
    // **静默丢掉** —— 丢了会让分母对不上，而那才是最难查的
    const s = platformSlices(counts([bucket('kimi2', 7, 3)]), OPTIONS)

    expect(s).toHaveLength(1)
    expect(s[0].code).toBe('kimi2')
    expect(s[0].label).toBe('kimi2')
  })

  it('series 为空时返回空数组，不炸', () => {
    expect(platformSlices(counts([]), OPTIONS)).toEqual([])
  })
})

describe('denominatorParts', () => {
  it('多平台时给出构成', () => {
    // §4.0 第 1 条：单平台 `21/35` 够了，多平台不够 —— **构成才决定这个数的含义**。
    // 两个平台表现完全没变，其中一个挂掉一半就能让总数从 50% 涨到 60%。
    const s = platformSlices(counts([bucket('deepseek', 30, 18), bucket('tongyi', 5, 4)]), OPTIONS)

    expect(denominatorParts(s)).toEqual([
      { label: 'DeepSeek', n: 30 },
      { label: '通义千问', n: 5 },
    ])
  })

  it('单平台时不给构成 —— 界面不该凭空多一行', () => {
    const s = platformSlices(counts([bucket('deepseek', 30, 18)]), OPTIONS)

    expect(denominatorParts(s)).toEqual([])
  })
})

describe('platformBars', () => {
  it('转成 EmphasisBars 要的形状，本品标 own', () => {
    const s = platformSlices(counts([bucket('deepseek', 30, 18), bucket('tongyi', 5, 4)]), OPTIONS)

    expect(platformBars(s)).toEqual([
      { key: 'deepseek', label: 'DeepSeek', m: 18, n: 30, own: true },
      { key: 'tongyi', label: '通义千问', m: 4, n: 5, own: true },
    ])
  })

  it('分母为 0 的平台照样出条 —— 那是「这个平台没采到」，不是没有这个平台', () => {
    // rate(m, 0) 返回 null，EmphasisBars 会画成 `—`。
    // **把它过滤掉才是错的**：用户会以为那个平台压根没跑
    const s = platformSlices(counts([bucket('deepseek', 30, 18), bucket('doubao', 0, 0)]), OPTIONS)

    expect(platformBars(s).map((b) => b.n)).toEqual([30, 0])
  })
})
