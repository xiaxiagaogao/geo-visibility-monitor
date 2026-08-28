'use client'

import { useEffect, useState } from 'react'

import { SampleTable } from '@/components/runs/SampleTable'
import runs from '@/components/runs/runs.module.css'
import { Aside, Blank, Button, Fault, Pending } from '@/components/kit'
import { ApiError } from '@/lib/api/client'
import { countRunJobs } from '@/lib/api/crawl-jobs'
import { listRunSamples } from '@/lib/api/responses'
import { pageLabel } from '@/lib/l3/samples'
import type { RawResponseSummary } from '@/lib/types'

/** P2-37 联网筛选的四个档（含「全部」）。**三态各占一档，不合并** */
type SearchFilter = 'all' | 'true' | 'false' | 'unknown'

const SEARCH_TABS: { key: SearchFilter; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'true', label: '已联网' },
  { key: 'false', label: '未联网' },
  // **「未记录」必须自成一档。** 并进「未联网」就是把 P2-37 之前的
  // 55 条历史样本说成「确认没联网」——那是一句我们没测过的话
  { key: 'unknown', label: '未记录' },
]

/** 一页 20 条。**分页是这个页面的正常形态**，不是「先全拉下来再说」的临时方案 */
const PAGE_SIZE = 20

/**
 * 样本列表 tab 的内容。
 *
 * 取两路数：
 *   1. `/v1/responses/summary?run_id=` —— 这一页的样本（轻量投影，不带全文）
 *   2. `/v1/crawl-jobs?run_id=&status=failed` —— 只取 total
 *
 * **第二路不是锦上添花。** 失败的 job 不产出 RawResponse，所以它在样本表里
 * 一行都不占；不单独数一次的话，一个 partial 的 run 看起来就和完整跑完的
 * 一模一样，只是「碰巧少几条」。分母少掉的那一截必须自己说出来。
 *
 * 每翻一页两路都重取：failed 数在 run 还没跑完时会变，
 * 而这一路是 `limit=1` 的计数请求，便宜到不值得为它做缓存。
 */
export function SamplesPanel({
  runId,
  ownBrandId,
  taskId,
}: {
  runId: number
  ownBrandId: number
  /** 只用来拼证据页链接 —— 这一页的数字都来自 runId */
  taskId: number
}) {
  const [samples, setSamples] = useState<RawResponseSummary[] | null>(null)
  const [total, setTotal] = useState(0)
  const [failed, setFailed] = useState(0)
  const [offset, setOffset] = useState(0)
  const [error, setError] = useState<Error | null>(null)
  const [attempt, setAttempt] = useState(0)
  const [searchFilter, setSearchFilter] = useState<SearchFilter>('all')

  useEffect(() => {
    let alive = true
    setError(null)
    setSamples(null)
    Promise.all([
      listRunSamples({
        runId,
        limit: PAGE_SIZE,
        offset,
        // **服务端筛，不是前端筛** —— 列表是服务端分页的，
        // 在前端过滤只会过滤当前这一页，而用户看不出还有别的页
        searchUsed: searchFilter === 'all' ? undefined : searchFilter,
      }),
      countRunJobs({ runId, status: 'failed' }),
    ])
      .then(([page, failedCount]) => {
        if (!alive) return
        setSamples(page.items)
        setTotal(page.total)
        setFailed(failedCount)
      })
      .catch((e: unknown) => {
        if (alive) setError(e instanceof Error ? e : new Error(String(e)))
      })
    return () => {
      alive = false
    }
  }, [runId, offset, attempt, searchFilter])

  const changeFilter = (key: SearchFilter) => {
    // **切筛选必须回第一页。** 否则筛完只剩 3 条时 offset 还停在 20，
    // 页面会显示「这次运行没有样本」——一个纯属翻页造成的假空态
    setOffset(0)
    setSearchFilter(key)
  }

  if (error) {
    return (
      <Fault
        status={error instanceof ApiError ? error.status : 0}
        message={error instanceof ApiError ? error.detail : '加载失败'}
        onRetry={() => setAttempt((a) => a + 1)}
      />
    )
  }

  const filtering = searchFilter !== 'all'

  /** 筛选条。**任何状态下都要渲染**，理由见下面那个空态分支 */
  const tabs = (
    <div className={runs.filters}>
      <span className={runs.filterLabel}>联网</span>
      {SEARCH_TABS.map((t) => (
        <button
          key={t.key}
          type="button"
          className={runs.chip}
          onClick={() => changeFilter(t.key)}
          aria-pressed={searchFilter === t.key}
        >
          {t.label}
        </button>
      ))}
    </div>
  )

  if (samples === null) {
    return (
      <div>
        {tabs}
        <div style={{ display: 'grid', gap: 8 }}>
          <Pending height={22} />
          <Pending height={22} />
          <Pending height={22} />
        </div>
      </div>
    )
  }

  if (total === 0) {
    return (
      <div>
        {/* **筛选条必须留着。** 筛出 0 条时如果连筛选条一起收掉，
            用户就被困在一个空页面里、没有任何办法退回「全部」——
            而且会把「这一档没有样本」误读成「这次运行没有样本」 */}
        {tabs}
        {filtering ? (
          <Blank
            lead={`这次运行没有「${SEARCH_TABS.find((t) => t.key === searchFilter)?.label}」的样本`}
          >
            这是筛选的结果，不是这次运行没采到东西 —— 点「全部」看完整列表。
          </Blank>
        ) : (
          <Blank lead="这次运行没有样本">
            {failed > 0
              ? `${failed} 条采样全部失败，一条回答都没拿到 —— 这是采集出了问题，不是 AI 没提你的品牌。可以在任务头点「立即运行」重跑一次。`
              : '还没有采样回来。这次运行可能刚发起，用右上角重新载入看进度。'}
          </Blank>
        )}
      </div>
    )
  }

  const label = pageLabel(offset, samples.length, total)

  return (
    <div>
      {failed > 0 ? (
        <div style={{ marginBottom: 'var(--sp-4)' }}>
          <Aside tone="alert">
            另有 <strong>{failed}</strong> 条采样失败，没产出回答 ——
            <strong>它们不在下表里</strong>，也不在任何比率的分母里。
            分母少一截时所有比率都会偏高，别拿它和一次完整运行直接比。
          </Aside>
        </div>
      ) : null}

      {tabs}

      {/* 筛过之后必须说清「这不是全部」—— 否则下面那个 total 会被当成
          这次运行的样本总数，而它只是这一档的条数 */}
      {filtering ? (
        <div style={{ marginBottom: 'var(--sp-4)' }}>
          <Aside>
            当前只看「{SEARCH_TABS.find((t) => t.key === searchFilter)?.label}」这一档，
            <strong>下面的条数不是这次运行的全部样本</strong>。
          </Aside>
        </div>
      ) : null}

      <SampleTable samples={samples} ownBrandId={ownBrandId} taskId={taskId} runId={runId} />

      <div className={runs.pager}>
        <span className={runs.pagerInfo}>{label}</span>
        <div className={runs.pagerButtons}>
          <Button onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))} disabled={offset === 0}>
            上一页
          </Button>
          <Button
            onClick={() => setOffset(offset + PAGE_SIZE)}
            disabled={offset + samples.length >= total}
          >
            下一页
          </Button>
        </div>
      </div>
    </div>
  )
}
