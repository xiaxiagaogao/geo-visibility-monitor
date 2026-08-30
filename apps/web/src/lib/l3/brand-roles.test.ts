import { describe, expect, it } from 'vitest'

import type { Brand } from '@/lib/types'

import { classifyBrands, defaultMonitoredBrandId } from './brand-roles'

function brand(id: number, name: string, competitor_ids: number[] = []): Brand {
  return {
    id,
    workspace_id: 1,
    name,
    name_en: null,
    industry: null,
    aliases: [],
    competitor_ids,
    created_at: '2026-08-01T00:00:00Z',
  }
}

const task = (brand_id: number) => ({ brand_id })

describe('classifyBrands', () => {
  it('把有任务的品牌算成监测对象', () => {
    const b = [brand(1, '安踏'), brand(2, '耐克')]
    const r = classifyBrands(b, [task(1)])
    expect(r.monitored.map((m) => m.brand.name)).toEqual(['安踏', '耐克'])
    expect(r.monitored[0].taskCount).toBe(1)
  })

  it('被引为竞品、且自己没任务没竞品集的，是参照', () => {
    const b = [brand(1, '安踏', [2, 3]), brand(2, '耐克'), brand(3, '李宁')]
    const r = classifyBrands(b, [task(1)])
    expect(r.monitored.map((m) => m.brand.name)).toEqual(['安踏'])
    expect(r.reference.map((m) => m.brand.name)).toEqual(['耐克', '李宁'])
  })

  /**
   * 这条是整个模块存在的理由。反过来写判据（「有任务或有竞品集的才是监测对象」）
   * 会让刚建出来的品牌当场从列表里消失。
   */
  it('**刚新建、什么都还没配的品牌仍然是监测对象**', () => {
    const b = [brand(1, '安踏', [2]), brand(2, '耐克'), brand(9, '刚建的')]
    const r = classifyBrands(b, [task(1)])
    expect(r.monitored.map((m) => m.brand.name)).toContain('刚建的')
    expect(r.reference.map((m) => m.brand.name)).toEqual(['耐克'])
  })

  it('配了竞品集但还没建任务的，也是监测对象', () => {
    const b = [brand(1, '土巴兔', [2]), brand(2, '齐家网')]
    const r = classifyBrands(b, [])
    expect(r.monitored.map((m) => m.brand.name)).toEqual(['土巴兔'])
    expect(r.monitored[0].taskCount).toBe(0)
    expect(r.reference.map((m) => m.brand.name)).toEqual(['齐家网'])
  })

  it('一个品牌既被引为竞品、自己又有任务时，算监测对象', () => {
    // 两个客户互为竞品是真实场景，不能因为被引用就把人家降级
    const b = [brand(1, '安踏', [2]), brand(2, '李宁', [1])]
    const r = classifyBrands(b, [task(1), task(2)])
    expect(r.reference).toHaveLength(0)
    expect(r.monitored).toHaveLength(2)
  })

  it('自引不会把品牌自己判成参照', () => {
    const b = [brand(1, '安踏', [1])]
    const r = classifyBrands(b, [])
    expect(r.monitored.map((m) => m.brand.name)).toEqual(['安踏'])
    expect(r.reference).toHaveLength(0)
  })

  it('记下参照品牌是被谁引的 —— 否则它就找不回去了', () => {
    const b = [brand(1, '安踏', [3]), brand(2, '土巴兔', [3]), brand(3, '某牌')]
    const r = classifyBrands(b, [])
    expect(r.reference[0].referencedBy).toEqual([1, 2])
  })

  it('taskCount 数的是任务条数，不是布尔', () => {
    const r = classifyBrands([brand(1, '安踏')], [task(1), task(1), task(1)])
    expect(r.monitored[0].taskCount).toBe(3)
  })

  it('空输入不炸', () => {
    expect(classifyBrands([], [])).toEqual({ monitored: [], reference: [] })
  })
})

describe('defaultMonitoredBrandId', () => {
  it('优先落在有任务的品牌上 —— 引用只可能来自跑过的运行', () => {
    const b = [brand(1, '土巴兔', [3]), brand(2, '安踏'), brand(3, '齐家网')]
    const r = classifyBrands(b, [task(2)])
    expect(defaultMonitoredBrandId(r)).toBe(2)
  })

  it('没有任务时退到第一个监测对象', () => {
    const r = classifyBrands([brand(7, '土巴兔', [8]), brand(8, '齐家网')], [])
    expect(defaultMonitoredBrandId(r)).toBe(7)
  })

  it('一个监测对象都没有时返回 null，不瞎选', () => {
    expect(defaultMonitoredBrandId({ monitored: [], reference: [] })).toBeNull()
  })
})
