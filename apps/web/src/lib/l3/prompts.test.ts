import { describe, expect, it } from 'vitest'

import type { Prompt } from '../types'

import { activeCount, categoryLabel, groupByCategory } from './prompts'

const p = (id: number, category: string | null, is_active = true): Prompt => ({
  id,
  brand_id: 34,
  text: `提问 ${id}`,
  category,
  tags: [],
  is_active,
  created_at: '2026-08-01T00:00:00Z',
})

describe('categoryLabel', () => {
  it('已知类别给中文名', () => {
    expect(categoryLabel('unprompted')).toBe('无提示提问')
    expect(categoryLabel('scenario')).toBe('场景提问')
  })

  it('未知类别**原样显示**，不吞进「其他」', () => {
    // 后端随时可能加新类别。映射不到就并进「其他」的话，界面上会出现
    // 一堆看不出区别的行，而它们其实分属不同类别
    expect(categoryLabel('comparison')).toBe('comparison')
  })

  it('null 与空串都是「未分类」', () => {
    expect(categoryLabel(null)).toBe('未分类')
    expect(categoryLabel('')).toBe('未分类')
    expect(categoryLabel('   ')).toBe('未分类')
  })
})

describe('groupByCategory', () => {
  it('已知类别按声明顺序在前', () => {
    const groups = groupByCategory([p(1, 'scenario'), p(2, 'unprompted')])
    expect(groups.map((g) => g.category)).toEqual(['unprompted', 'scenario'])
  })

  it('未知类别排在已知之后，按首次出现', () => {
    const groups = groupByCategory([p(1, 'zzz'), p(2, 'aaa'), p(3, 'unprompted')])
    expect(groups.map((g) => g.category)).toEqual(['unprompted', 'zzz', 'aaa'])
  })

  it('「未分类」永远排最后 —— 它不是一个类别，是还没归类', () => {
    const groups = groupByCategory([p(1, null), p(2, 'unprompted')])
    expect(groups.map((g) => g.category)).toEqual(['unprompted', ''])
  })

  it('null 与空串归到同一组，不分裂成两组', () => {
    const groups = groupByCategory([p(1, null), p(2, ''), p(3, '  ')])
    expect(groups).toHaveLength(1)
    expect(groups[0].prompts.map((x) => x.id)).toEqual([1, 2, 3])
  })

  it('组内保持入参顺序', () => {
    const groups = groupByCategory([p(3, 'unprompted'), p(1, 'unprompted'), p(2, 'unprompted')])
    expect(groups[0].prompts.map((x) => x.id)).toEqual([3, 1, 2])
  })

  it('一条都不丢', () => {
    const input = [p(1, 'unprompted'), p(2, null), p(3, 'scenario'), p(4, 'x')]
    const total = groupByCategory(input).reduce((n, g) => n + g.prompts.length, 0)
    expect(total).toBe(input.length)
  })

  it('空数组给空分组', () => {
    expect(groupByCategory([])).toEqual([])
  })
})

describe('activeCount', () => {
  it('只数启用中的 —— 那才是下次运行会问出去的', () => {
    expect(activeCount([p(1, null, true), p(2, null, false), p(3, null, true)])).toBe(2)
  })

  it('一条都没启用时是 0 —— 下次运行会是 empty 状态', () => {
    // create_run 只冻结 is_active=true 的；全停用就一条 job 都建不出来，
    // 那是配置问题，不是采集失败
    expect(activeCount([p(1, null, false)])).toBe(0)
    expect(activeCount([])).toBe(0)
  })
})
