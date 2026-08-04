import { describe, expect, it } from 'vitest'

import { formatFraction, formatRate, headShare, matrixLevel, rate, sov } from './rates'

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

describe('sov', () => {
  it('对上 21/137 = 15.3%', () => {
    // 安踏 21，竞品 亚瑟士22 耐克21 李宁20 阿迪20 361度17 特步11 鸿星尔克5 = 116
    expect(sov(21, [22, 21, 20, 20, 17, 11, 5])).toBeCloseTo(21 / 137, 10)
  })

  it('全场零提及 → 分母 0 → null', () => {
    expect(sov(0, [0, 0])).toBeNull()
  })

  it('没有竞品时就是 100%', () => {
    expect(sov(7, [])).toBe(1)
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
