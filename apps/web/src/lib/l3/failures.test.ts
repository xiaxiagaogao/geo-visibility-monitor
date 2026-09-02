import { describe, expect, it } from 'vitest'

import type { CrawlJob, FailureKind } from '@/lib/types'

import { backoffPending, failureBreakdown, needsHumanAction } from './failures'

function job(
  id: number,
  status: CrawlJob['status'],
  failure_kind: FailureKind | null = null,
  next_attempt_at: string | null = null,
): CrawlJob {
  return {
    id,
    prompt_id: 1,
    platform: 'tongyi',
    status,
    sample_index: 0,
    error_message: null,
    failure_kind,
    attempt: null,
    next_attempt_at,
    started_at: null,
    finished_at: null,
    created_at: '2026-08-23T00:00:00Z',
    response_id: null,
  }
}

describe('failureBreakdown', () => {
  /**
   * 这条是整个模块存在的理由，接口文档点名要求过：
   * `null` = 还没失败过（在 failed 上出现就是后端异常）；
   * `unknown` = 失败了但没认出来。排查方向完全不同。
   */
  it('**null 与 unknown 必须分开，不许合并成一个词**', () => {
    const b = failureBreakdown([
      job(1, 'failed', null),
      job(2, 'failed', 'unknown'),
      job(3, 'failed', 'unknown'),
    ])
    expect(b.unclassified).toBe(1)
    expect(b.groups).toHaveLength(1)
    expect(b.groups[0].kind).toBe('unknown')
    expect(b.groups[0].count).toBe(2)
    // 没分类的**不算进** classified
    expect(b.classified).toBe(2)
  })

  it('要人动手的排在能自愈的前面', () => {
    const b = failureBreakdown([
      job(1, 'failed', 'timeout'),
      job(2, 'failed', 'login_required'),
      job(3, 'failed', 'rate_limited'),
      job(4, 'failed', 'parse_error'),
    ])
    expect(b.groups.map((g) => g.kind)).toEqual([
      'login_required',
      'parse_error',
      'rate_limited',
      'timeout',
    ])
  })

  it('只统计真的失败了的 —— 退避中的 pending 不算', () => {
    // 退避中的 job 状态仍是 pending，身上带的 failure_kind 是上次尝试的痕迹
    const b = failureBreakdown([
      job(1, 'pending', 'timeout', '2099-01-01T00:00:00Z'),
      job(2, 'failed', 'timeout'),
      job(3, 'success'),
      job(4, 'running'),
    ])
    expect(b.classified).toBe(1)
    expect(b.groups[0].count).toBe(1)
  })

  it('每一类都带上标签和下一步动作', () => {
    const b = failureBreakdown([job(1, 'failed', 'login_required')])
    expect(b.groups[0].label).toBe('登录态过期')
    expect(b.groups[0].action).toMatch(/storage_state/)
    expect(b.groups[0].autoRetried).toBe(false)
  })

  it('自动重试的两类标成 autoRetried', () => {
    const b = failureBreakdown([job(1, 'failed', 'timeout'), job(2, 'failed', 'rate_limited')])
    expect(b.groups.every((g) => g.autoRetried)).toBe(true)
  })

  it('没有失败时返回空，不返回一堆 0', () => {
    const b = failureBreakdown([job(1, 'success'), job(2, 'pending')])
    expect(b).toEqual({ groups: [], classified: 0, unclassified: 0 })
  })

  it('空输入不炸', () => {
    expect(failureBreakdown([])).toEqual({ groups: [], classified: 0, unclassified: 0 })
  })
})

describe('needsHumanAction', () => {
  it('全是能自愈的 → 不用人动手', () => {
    const b = failureBreakdown([job(1, 'failed', 'timeout'), job(2, 'failed', 'rate_limited')])
    expect(needsHumanAction(b)).toBe(false)
  })

  it('有一条要换登录态就得动手', () => {
    const b = failureBreakdown([job(1, 'failed', 'timeout'), job(2, 'failed', 'login_required')])
    expect(needsHumanAction(b)).toBe(true)
  })

  /** 后端没分类本身就是异常，得有人去看 */
  it('有没分类的也算要动手', () => {
    const b = failureBreakdown([job(1, 'failed', null)])
    expect(needsHumanAction(b)).toBe(true)
  })
})

describe('backoffPending', () => {
  const now = new Date('2026-08-23T12:00:00Z')

  it('数的是 next_attempt_at 在未来的 pending —— 那是正在自动重试', () => {
    const n = backoffPending(
      [
        job(1, 'pending', 'timeout', '2026-08-23T12:05:00Z'),
        job(2, 'pending', null, null), // 还没轮到，不是退避
        job(3, 'pending', 'timeout', '2026-08-23T11:00:00Z'), // 时间已过
        job(4, 'failed', 'timeout', '2026-08-23T13:00:00Z'), // 已终态
      ],
      now,
    )
    expect(n).toBe(1)
  })

  it('一条都没有时是 0', () => {
    expect(backoffPending([job(1, 'success')], now)).toBe(0)
  })
})
