import { describe, expect, it } from 'vitest'

import type { CountsResponse, Run, RunStatus } from '@/lib/types'

import { buildTrend, comparableSegments, incompleteCount, timeAxis } from './trend'

function run(
  id: number,
  at: string,
  platforms: string[],
  status: RunStatus = 'success',
  note: string | null = null,
): Run {
  return { id, task_id: 27, platforms, note, created_at: at, status, n_jobs: 21 }
}

function counts(m: number, n: number, comps: number[] = []): CountsResponse {
  return {
    brand_id: 34,
    filters: {},
    group_by: 'none',
    denominator: {
      definition: 'answer_status=ok',
      n_valid: n,
      n_total_responses: n,
      n_empty: 0,
      n_too_short: 0,
      n_error: 0,
      n_unannotated: 0,
    },
    brand: {
      brand_id: 34,
      m_mentioned: m,
      m_body: m,
      m_citation_only: 0,
      m_none: n - m,
      m_head: m,
      m_middle: 0,
      m_tail: 0,
    },
    competitors: comps.map((cm, i) => ({
      brand_id: 100 + i,
      m_mentioned: cm,
      m_body: cm,
      m_citation_only: 0,
      m_none: n - cm,
      m_head: cm,
      m_middle: 0,
      m_tail: 0,
    })),
    series: [],
    note: '',
  }
}

const map = (...pairs: [number, CountsResponse][]) => new Map(pairs)

describe('buildTrend', () => {
  it('按时间升序排，不按传入顺序', () => {
    const points = buildTrend(
      [
        run(300, '2026-08-23T03:47:00Z', ['tongyi']),
        run(297, '2026-08-17T03:46:00Z', ['tongyi']),
        run(298, '2026-08-17T06:51:00Z', ['tongyi']),
      ],
      map([300, counts(12, 18)], [297, counts(9, 20)], [298, counts(15, 30)]),
    )
    expect(points.map((p) => p.runId)).toEqual([297, 298, 300])
  })

  it('取不到 counts 的 run 直接不出现 —— 绝不在轴上补一个 0', () => {
    const points = buildTrend(
      [
        run(1, '2026-08-16T00:00:00Z', ['tongyi']),
        run(2, '2026-08-17T00:00:00Z', ['tongyi']),
      ],
      map([1, counts(3, 10)]),
    )
    expect(points).toHaveLength(1)
    expect(points[0].runId).toBe(1)
  })

  it('分母为 0 时 r 是 null，不是 0', () => {
    const points = buildTrend([run(1, '2026-08-16T00:00:00Z', ['tongyi'])], map([1, counts(0, 0)]))
    expect(points[0].r).toBeNull()
  })

  it('真的是 0 时 r 是 0，不是 null', () => {
    const points = buildTrend([run(1, '2026-08-16T00:00:00Z', ['tongyi'])], map([1, counts(0, 12)]))
    expect(points[0].r).toBe(0)
  })

  it('平台集变化标成 platforms 断口', () => {
    const points = buildTrend(
      [
        run(1, '2026-08-16T00:00:00Z', ['deepseek', 'tongyi']),
        run(2, '2026-08-17T00:00:00Z', ['tongyi']),
      ],
      map([1, counts(5, 10)], [2, counts(6, 10)]),
    )
    expect(points[0].breaks).toEqual([])
    expect(points[1].breaks).toContain('platforms')
  })

  it('平台顺序不同但集合相同 —— 不算断口', () => {
    const points = buildTrend(
      [
        run(1, '2026-08-16T00:00:00Z', ['tongyi', 'deepseek']),
        run(2, '2026-08-17T00:00:00Z', ['deepseek', 'tongyi']),
      ],
      map([1, counts(5, 10)], [2, counts(6, 10)]),
    )
    expect(points[1].breaks).not.toContain('platforms')
  })

  it('带 note 的 run 标成 note 软信号，第一个点也能有', () => {
    const points = buildTrend(
      [run(1, '2026-08-16T00:00:00Z', ['tongyi'], 'success', 'deepseek 已摘掉')],
      map([1, counts(5, 10)]),
    )
    expect(points[0].breaks).toEqual(['note'])
  })

  it('空白 note 不算信号', () => {
    const points = buildTrend(
      [run(1, '2026-08-16T00:00:00Z', ['tongyi'], 'success', '   ')],
      map([1, counts(5, 10)]),
    )
    expect(points[0].breaks).toEqual([])
  })

  it.each<[RunStatus, boolean]>([
    ['success', false],
    ['partial', true],
    ['pending', true],
    ['running', true],
  ])('status=%s 的 incomplete 是 %s', (status, expected) => {
    const points = buildTrend(
      [run(1, '2026-08-16T00:00:00Z', ['tongyi'], status)],
      map([1, counts(5, 10)]),
    )
    expect(points[0].incomplete).toBe(expected)
  })
})

describe('timeAxis', () => {
  it('按真实时间间隔排，不是等距', () => {
    const points = buildTrend(
      [
        run(1, '2026-08-16T00:00:00Z', ['t']),
        run(2, '2026-08-17T00:00:00Z', ['t']),
        run(3, '2026-08-20T00:00:00Z', ['t']),
      ],
      map([1, counts(1, 10)], [2, counts(2, 10)], [3, counts(3, 10)]),
    )
    // 16→17 是 1 天、17→20 是 3 天，总跨度 4 天 → 第二点应落在 1/4
    expect(timeAxis(points)).toEqual([0, 0.25, 1])
  })

  it('时间全相同时退化成等距，不产生 NaN', () => {
    const points = buildTrend(
      [run(1, '2026-08-16T00:00:00Z', ['t']), run(2, '2026-08-16T00:00:00Z', ['t'])],
      map([1, counts(1, 10)], [2, counts(2, 10)]),
    )
    const axis = timeAxis(points)
    expect(axis).toEqual([0, 1])
    expect(axis.every(Number.isFinite)).toBe(true)
  })

  it('单点落在中间；空数组返回空', () => {
    const points = buildTrend([run(1, '2026-08-16T00:00:00Z', ['t'])], map([1, counts(1, 10)]))
    expect(timeAxis(points)).toEqual([0.5])
    expect(timeAxis([])).toEqual([])
  })
})

describe('comparableSegments', () => {
  it('平台断口切段', () => {
    const points = buildTrend(
      [
        run(1, '2026-08-16T00:00:00Z', ['deepseek', 'tongyi']),
        run(2, '2026-08-17T00:00:00Z', ['deepseek', 'tongyi']),
        run(3, '2026-08-18T00:00:00Z', ['tongyi']),
      ],
      map([1, counts(1, 10)], [2, counts(2, 10)], [3, counts(3, 10)]),
    )
    const segs = comparableSegments(points)
    expect(segs.map((s) => s.map((p) => p.runId))).toEqual([[1, 2], [3]])
  })

  it('note 是软信号，**不切段** —— 拿它切等于替读者下了没依据的结论', () => {
    const points = buildTrend(
      [
        run(1, '2026-08-16T00:00:00Z', ['tongyi']),
        run(2, '2026-08-17T00:00:00Z', ['tongyi'], 'success', '换了个提问词'),
      ],
      map([1, counts(1, 10)], [2, counts(2, 10)]),
    )
    expect(comparableSegments(points)).toHaveLength(1)
  })

  it('空序列返回空，不返回 [[]]', () => {
    expect(comparableSegments([])).toEqual([])
  })
})

describe('incompleteCount', () => {
  it('数出分母不完整的运行次数', () => {
    const points = buildTrend(
      [
        run(1, '2026-08-16T00:00:00Z', ['t'], 'success'),
        run(2, '2026-08-17T00:00:00Z', ['t'], 'partial'),
        run(3, '2026-08-18T00:00:00Z', ['t'], 'partial'),
      ],
      map([1, counts(1, 10)], [2, counts(2, 10)], [3, counts(3, 10)]),
    )
    expect(incompleteCount(points)).toBe(2)
  })
})

describe('competitorBand', () => {
  it('取竞品提及率的最低与最高，且与本品共用同一个分母', () => {
    const points = buildTrend(
      [run(1, '2026-08-16T00:00:00Z', ['t'])],
      map([1, counts(5, 10, [2, 8, 6])]),
    )
    expect(points[0].competitorBand).toEqual({ min: 0.2, max: 0.8 })
  })

  it('没有竞品时是 null —— 不画一条贴地的带子冒充「竞品都是 0」', () => {
    const points = buildTrend([run(1, '2026-08-16T00:00:00Z', ['t'])], map([1, counts(5, 10)]))
    expect(points[0].competitorBand).toBeNull()
  })

  it('分母为 0 时是 null，不是 {min:0,max:0}', () => {
    const points = buildTrend(
      [run(1, '2026-08-16T00:00:00Z', ['t'])],
      map([1, counts(0, 0, [0, 0])]),
    )
    expect(points[0].competitorBand).toBeNull()
  })
})
