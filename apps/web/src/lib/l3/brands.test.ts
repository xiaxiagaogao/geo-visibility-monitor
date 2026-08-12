import { describe, expect, it } from 'vitest'

import {
  formatAliasLines,
  normalizeAliases,
  parseAliasLines,
  sameList,
  sanitizeCompetitorIds,
  toggleCompetitor,
} from './brands'

describe('normalizeAliases —— 与后端 _normalize_aliases 同口径', () => {
  it('去首尾空白', () => {
    expect(normalizeAliases(['  安踏  ', 'ANTA '])).toEqual(['安踏', 'ANTA'])
  })

  it('丢掉空串和纯空白', () => {
    expect(normalizeAliases(['安踏', '', '   ', '\t'])).toEqual(['安踏'])
  })

  it('大小写不敏感去重，**保留首次出现的写法**', () => {
    // 后端存的是首次出现那一条的原样，不是全小写 —— 展示时要和库里一致
    expect(normalizeAliases(['Nike', 'nike', 'NIKE'])).toEqual(['Nike'])
    expect(normalizeAliases(['nike', 'Nike'])).toEqual(['nike'])
  })

  it('保持顺序', () => {
    expect(normalizeAliases(['c', 'a', 'b'])).toEqual(['c', 'a', 'b'])
  })

  it('中文不受大小写折叠影响', () => {
    expect(normalizeAliases(['安踏', '安踏体育'])).toEqual(['安踏', '安踏体育'])
  })

  it('空数组还是空数组 —— 清空别名是合法操作', () => {
    // PUT 一个空列表就是「删光所有别名」，这是整体替换语义的正常用法，
    // 不该被当成「没填」而拦下
    expect(normalizeAliases([])).toEqual([])
  })
})

describe('parseAliasLines / formatAliasLines', () => {
  it('一行一个，往返一致', () => {
    const aliases = ['安踏', 'ANTA', '安踏体育']
    expect(parseAliasLines(formatAliasLines(aliases))).toEqual(aliases)
  })

  it('中间的空行被丢掉，不产生空别名', () => {
    expect(parseAliasLines('安踏\n\n\nANTA\n')).toEqual(['安踏', 'ANTA'])
  })

  it('空文本框 = 清空别名，不是「没改」', () => {
    expect(parseAliasLines('')).toEqual([])
    expect(parseAliasLines('\n\n')).toEqual([])
  })
})

describe('sanitizeCompetitorIds —— 与后端 replace_competitors 同口径', () => {
  const known = [34, 35, 36, 41]

  it('挡掉自己 —— 后端是 400，这里直接不让它进列表', () => {
    expect(sanitizeCompetitorIds([35, 34, 36], 34, known)).toEqual([35, 36])
  })

  it('去重，保留首次出现的位置', () => {
    expect(sanitizeCompetitorIds([36, 35, 36], 34, known)).toEqual([36, 35])
  })

  it('挡掉不存在的品牌 id', () => {
    expect(sanitizeCompetitorIds([35, 999], 34, known)).toEqual([35])
  })

  it('保持顺序 —— 竞品顺序就是矩阵的列顺序，不许自作主张排序', () => {
    expect(sanitizeCompetitorIds([41, 35, 36], 34, known)).toEqual([41, 35, 36])
  })

  it('空列表合法 —— 一个竞品都不比是正常配置', () => {
    expect(sanitizeCompetitorIds([], 34, known)).toEqual([])
  })
})

describe('toggleCompetitor', () => {
  it('没选就加到末尾', () => {
    expect(toggleCompetitor([35, 36], 41)).toEqual([35, 36, 41])
  })

  it('选了就移除', () => {
    expect(toggleCompetitor([35, 36, 41], 36)).toEqual([35, 41])
  })

  it('不改原数组', () => {
    const before = [35, 36]
    toggleCompetitor(before, 41)
    expect(before).toEqual([35, 36])
  })
})

describe('sameList', () => {
  it('内容与顺序都一样才算没变', () => {
    expect(sameList([1, 2, 3], [1, 2, 3])).toBe(true)
    expect(sameList([1, 2, 3], [1, 3, 2])).toBe(false)
    expect(sameList([1, 2], [1, 2, 3])).toBe(false)
  })

  it('**顺序敏感是刻意的** —— 竞品顺序就是矩阵列顺序，调序是真的改了东西', () => {
    // 若按集合比较，用户拖完顺序会发现保存按钮是灰的，而他确实改了配置
    expect(sameList([35, 36], [36, 35])).toBe(false)
  })

  it('空列表相等', () => {
    expect(sameList([], [])).toBe(true)
  })
})
