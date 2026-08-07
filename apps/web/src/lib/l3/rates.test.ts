import { describe, expect, it } from 'vitest'

import {
  firstMentionRate,
  formatFraction,
  formatRate,
  headShare,
  matrixLevel,
  rate,
} from './rates'

describe('rate', () => {
  it('0 命中是真结论，不是不可算', () => {
    expect(rate(0, 10)).toBe(0)
  })

  it('无分母 → null，不许显示 0%', () => {
    expect(rate(5, 0)).toBeNull()
    expect(rate(0, 0)).toBeNull()
    expect(rate(1, -3)).toBeNull()
  })

  it('对上安踏真实数据 21/35', () => {
    expect(rate(21, 35)).toBeCloseTo(0.6, 10)
  })

  it('NaN 不许悄悄变成 0', () => {
    expect(rate(Number.NaN, 35)).toBeNull()
  })
})

describe('headShare', () => {
  it('对上 15/21 = 71.4%', () => {
    expect(headShare(15, 21)).toBeCloseTo(0.714285, 5)
  })

  it('一次都没被提及时不可算', () => {
    expect(headShare(0, 0)).toBeNull()
  })
})

describe('firstMentionRate', () => {
  it('分母是被提及数，不是有效样本数', () => {
    // 21 次被提及里有 9 次排在第一个 —— 分母是 21 不是 35
    expect(firstMentionRate(9, 21)).toBeCloseTo(9 / 21, 10)
  })

  it('还没被提及过就不可算，不能显示 0%', () => {
    expect(firstMentionRate(0, 0)).toBeNull()
  })
})

describe('matrixLevel', () => {
  it('0% 是空心格，不是最暗档', () => {
    expect(matrixLevel(0)).toBe('zero')
    expect(matrixLevel(null)).toBe('zero')
  })

  it('按 ≤33% / 34–66% / ≥67% 分档', () => {
    expect(matrixLevel(1 / 3)).toBe('l1')
    expect(matrixLevel(0.5)).toBe('l2')
    expect(matrixLevel(2 / 3)).toBe('l2')
    expect(matrixLevel(0.9)).toBe('l3')
    expect(matrixLevel(1)).toBe('l3')
  })
})

describe('formatRate', () => {
  it('null 显示 —', () => {
    expect(formatRate(null)).toBe('—')
  })

  it('保留 1 位小数', () => {
    expect(formatRate(0.6)).toBe('60.0%')
    expect(formatRate(21 / 35)).toBe('60.0%')
    expect(formatRate(0)).toBe('0.0%')
    expect(formatRate(15 / 21)).toBe('71.4%')
  })
})

describe('formatFraction', () => {
  it('比率旁边永远跟着 m / n', () => {
    expect(formatFraction(21, 35)).toBe('21 / 35')
    expect(formatFraction(0, 13)).toBe('0 / 13')
  })
})
