/**
 * counts 取数层 —— 只验「URL 拼对没有」。
 *
 * 这一层错了都是安静地错：少一个 `run_id` 分母就变成该品牌历史全部混算，
 * 少一个 `platform` 命中矩阵就跨平台混算（P2-09 要解的正是后者）。
 * 两种都不会报错，只是数字悄悄不对。
 */
import { afterEach, describe, expect, it, vi } from 'vitest'

import { fetchRunCounts } from './counts'

function mockFetch() {
  const fn = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    headers: new Headers({ 'content-type': 'application/json' }),
    json: async () => ({}),
    text: async () => '{}',
  })
  globalThis.fetch = fn as unknown as typeof fetch
  return fn
}

function urlOf(fn: ReturnType<typeof mockFetch>): string {
  return String(fn.mock.calls[0][0])
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('fetchRunCounts', () => {
  it('总是带 brand_id 与 run_id', () => {
    const fn = mockFetch()
    void fetchRunCounts({ brandId: 34, runId: 296 })

    const u = urlOf(fn)
    expect(u).toContain('brand_id=34')
    expect(u).toContain('run_id=296')
  })

  it('带上 platform —— 命中矩阵强制单平台靠它', () => {
    // §4.0 第 3 条：命中矩阵强制单平台。**后端早就支持这个参数**
    // （`api/counts.py`），P2-09 之前前端一次都没传过 —— 于是勾两个平台
    // 建的任务，KPI 与矩阵会**静默混算**。
    const fn = mockFetch()
    void fetchRunCounts({ brandId: 34, runId: 296, platform: 'tongyi' })

    expect(urlOf(fn)).toContain('platform=tongyi')
  })

  it('不传 platform 时 URL 里不出现这个键', () => {
    // 传 `platform=undefined` 会拼出 `platform=undefined` 字面量，
    // 后端拿它当平台代码去比，结果是 0 条 —— 而这不会报错
    const fn = mockFetch()
    void fetchRunCounts({ brandId: 34, runId: 296, groupBy: 'prompt' })

    expect(urlOf(fn)).not.toContain('platform')
  })

  it('group_by=platform 是分平台面板的数据源，一次请求', () => {
    const fn = mockFetch()
    void fetchRunCounts({ brandId: 34, runId: 296, groupBy: 'platform' })

    expect(urlOf(fn)).toContain('group_by=platform')
  })
})
