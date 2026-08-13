import { describe, expect, it } from 'vitest'

import { escapeCsvField, neutralizeFormula, safeFileName, toCsv } from './csv'

describe('neutralizeFormula —— 这是安全问题不是格式问题', () => {
  it('挡住以 = 开头的公式', () => {
    // 提问词由运营自由输入，导出的文件在**别人的 Excel** 里打开。
    // 不中和的话这一条会变成可点的钓鱼链接，而表格看起来完全正常
    expect(neutralizeFormula('=HYPERLINK("http://evil","季度报表")')).toBe(
      '\'=HYPERLINK("http://evil","季度报表")',
    )
  })

  it('+ - @ 以及制表/回车开头同样要挡', () => {
    for (const c of ['+', '-', '@', '\t', '\r']) {
      expect(neutralizeFormula(`${c}x`).startsWith("'")).toBe(true)
    }
  })

  it('正常文本不动它', () => {
    expect(neutralizeFormula('2026年跑步鞋哪个品牌好？')).toBe('2026年跑步鞋哪个品牌好？')
    expect(neutralizeFormula('安踏')).toBe('安踏')
  })

  it('负数会被加引号 —— 这是刻意的取舍', () => {
    // -5 确实以 - 开头。让一个负数显示成文本，好过给公式注入留口子；
    // 而这份表里的数字列都是非负的（命中数、失分量），不会撞上
    expect(neutralizeFormula('-5')).toBe("'-5")
  })
})

describe('escapeCsvField —— RFC 4180', () => {
  it('含逗号的整体加引号', () => {
    expect(escapeCsvField('耐克, 阿迪')).toBe('"耐克, 阿迪"')
  })

  it('含引号的：整体加引号且内部引号翻倍', () => {
    expect(escapeCsvField('他说"很好"')).toBe('"他说""很好"""')
  })

  it('含换行的整体加引号 —— 提问词可能是多行的', () => {
    expect(escapeCsvField('第一行\n第二行')).toBe('"第一行\n第二行"')
  })

  it('null / undefined 变空串，不是字面量 "null"', () => {
    expect(escapeCsvField(null)).toBe('')
    expect(escapeCsvField(undefined)).toBe('')
  })

  it('数字原样', () => {
    expect(escapeCsvField(0)).toBe('0')
    expect(escapeCsvField(35)).toBe('35')
  })
})

describe('toCsv', () => {
  it('带 UTF-8 BOM —— 不带 Excel 打开中文全是乱码', () => {
    expect(toCsv([['提问']]).startsWith('﻿')).toBe(true)
  })

  it('换行用 CRLF', () => {
    expect(toCsv([['a'], ['b']])).toBe('﻿a\r\nb\r\n')
  })

  it('空表也给合法输出，不抛', () => {
    expect(toCsv([])).toBe('﻿\r\n')
  })
})

describe('safeFileName', () => {
  it('干掉路径分隔符与 Windows 保留字符', () => {
    expect(safeFileName('安踏/周度: 监测*')).toBe('安踏_周度_ 监测_')
  })

  it('空名字给个兜底，不生成一个没有名字的文件', () => {
    expect(safeFileName('   ')).toBe('export')
  })
})
