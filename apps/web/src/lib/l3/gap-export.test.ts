import { describe, expect, it } from 'vitest'

import { gapCsvFileName, gapCsvRows, GAP_CSV_HEADER } from './gap-export'
import type { Gap } from './gaps'

const gap = (over: Partial<Gap> = {}): Gap => ({
  promptId: 109,
  n: 5,
  ownM: 0,
  tier: 'absent',
  competitorsPresent: [
    { brandId: 36, m: 5 },
    { brandId: 41, m: 3 },
  ],
  score: 13,
  priority: 'high',
  ...over,
})

const promptText = new Map([[109, '2026年跑步鞋哪个品牌好']])
const brandName = new Map([
  [36, '耐克'],
  [41, '亚瑟士'],
])

describe('gapCsvRows', () => {
  it('第一行是表头', () => {
    const rows = gapCsvRows({ gaps: [], promptText, brandName })
    expect(rows[0]).toEqual([...GAP_CSV_HEADER])
  })

  it('本品命中与有效样本是两列，不拼成 3/5', () => {
    // Excel 会把 3/5 当成日期转成「3月5日」——一份发给别人的表格里出现这个，
    // 没人看得出原本是个分数
    const [, row] = gapCsvRows({ gaps: [gap({ ownM: 3, n: 5 })], promptText, brandName })
    expect(row[2]).toBe(3)
    expect(row[3]).toBe(5)
    expect(row.join('|')).not.toContain('3/5')
  })

  it('失分量必须在导出里 —— 它是排序依据', () => {
    // 没有它，收表的人只能按缺口类型分组，而那个分不出轻重
    const [, row] = gapCsvRows({ gaps: [gap({ score: 13 })], promptText, brandName })
    expect(row).toContain(13)
  })

  it('提问正文取自快照；取不到时给 #id，不留空白', () => {
    const [, row] = gapCsvRows({ gaps: [gap()], promptText: new Map(), brandName })
    expect(row[0]).toBe('提问 #109')
  })

  it('竞品名在前、命中数在后 —— 名字打头就不会被 Excel 当成日期', () => {
    const [, row] = gapCsvRows({ gaps: [gap()], promptText, brandName })
    expect(row[7]).toBe('耐克 5 · 亚瑟士 3')
  })

  it('竞品名取不到时给 #id', () => {
    const [, row] = gapCsvRows({ gaps: [gap()], promptText, brandName: new Map() })
    expect(row[7]).toBe('#36 5 · #41 3')
  })

  it('比率按 m/n 现算，分母为 0 时是 —', () => {
    const [, row] = gapCsvRows({ gaps: [gap({ ownM: 0, n: 0 })], promptText, brandName })
    expect(row[4]).toBe('—')
  })

  it('空清单只有表头，不生成一个只有 BOM 的空文件', () => {
    expect(gapCsvRows({ gaps: [], promptText, brandName })).toHaveLength(1)
  })
})

describe('gapCsvFileName', () => {
  it('上下文全在文件名里：任务 · 哪次运行 · 日期', () => {
    expect(gapCsvFileName('安踏监测集', 54, '2026-08-12T05:44:00Z')).toBe(
      '缺口清单_安踏监测集_run54_2026-08-12.csv',
    )
  })
})
