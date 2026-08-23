import { describe, expect, it } from 'vitest'

import type { CitationDomainsResult } from '@/lib/types'

import { citationCoverage, citationRows, citationScaleMax } from './citations'

const result = (
  items: [string, number, number][],
  total = items.reduce((s, [, c]) => s + c, 0),
  domains = items.length,
): CitationDomainsResult => ({
  n_citations: total,
  n_domains: domains,
  items: items.map(([domain, n_citations, n_samples]) => ({ domain, n_citations, n_samples })),
})

describe('citationRows', () => {
  it('名次照后端给的顺序，不在前端重排', () => {
    const rows = citationRows(result([['b.com', 5, 5], ['a.com', 9, 3]]))
    expect(rows.map((r) => [r.rank, r.domain])).toEqual([
      [1, 'b.com'],
      [2, 'a.com'],
    ])
  })

  it('算出平均每条样本引几次', () => {
    const rows = citationRows(result([['a.com', 9, 3]]))
    expect(rows[0].perSample).toBe(3)
  })

  it('n_samples 为 0 时 perSample 是 null —— 不可算，不是 0', () => {
    const rows = citationRows(result([['a.com', 4, 0]]))
    expect(rows[0].perSample).toBeNull()
  })

  it('真实数据里的那两行：toutiao 判为集中，163 不判', () => {
    const rows = citationRows(
      result([
        ['www.163.com', 12, 12],
        ['www.toutiao.com', 9, 4],
      ]),
    )
    expect(rows[0].concentrated).toBe(false) // 12 次来自 12 条 —— 覆盖面广
    expect(rows[1].concentrated).toBe(true) //  9 次只来自 4 条 —— 反复引
  })

  it('恰好 2 倍算集中（阈值是 >=，不是 >）', () => {
    expect(citationRows(result([['a.com', 6, 3]]))[0].concentrated).toBe(true)
  })

  it('总数不足 3 时不判集中 —— 一条回答里引两次说明不了任何事', () => {
    expect(citationRows(result([['a.com', 2, 1]]))[0].concentrated).toBe(false)
  })

  it('每条样本各引一次的站不判集中', () => {
    expect(citationRows(result([['a.com', 8, 8]]))[0].concentrated).toBe(false)
  })
})

describe('citationCoverage', () => {
  it('total 取全集，不是 items 的和 —— 这是 API.md §4 明确警告过的坑', () => {
    // 榜上 3 行共 20 次，但全集有 144 次
    const cov = citationCoverage(result([['a', 10, 5], ['b', 6, 6], ['c', 4, 4]], 144, 40))
    expect(cov.listed).toBe(20)
    expect(cov.total).toBe(144)
    expect(cov.domains).toBe(40)
    expect(cov.truncated).toBe(true)
    expect(cov.share).toBeCloseTo(20 / 144)
  })

  it('没被截断时 truncated 是 false', () => {
    const cov = citationCoverage(result([['a', 10, 5]], 10, 1))
    expect(cov.truncated).toBe(false)
    expect(cov.share).toBe(1)
  })

  it('全集为 0 时 share 是 null，不是 0', () => {
    const cov = citationCoverage(result([], 0, 0))
    expect(cov.share).toBeNull()
    expect(cov.listed).toBe(0)
  })
})

describe('citationScaleMax', () => {
  it('取榜首的引用次数，好让第一行画满', () => {
    const rows = citationRows(result([['a', 12, 12], ['b', 9, 4]]))
    expect(citationScaleMax(rows)).toBe(12)
  })

  it('空榜返回 0', () => {
    expect(citationScaleMax([])).toBe(0)
  })
})
