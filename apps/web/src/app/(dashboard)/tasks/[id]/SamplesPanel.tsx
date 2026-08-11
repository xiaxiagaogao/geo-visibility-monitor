'use client'

import { useEffect, useState } from 'react'

import { SampleTable } from '@/components/runs/SampleTable'
import runs from '@/components/runs/runs.module.css'
import { Button, EmptyState, ErrorState, PanelNote, Skeleton } from '@/components/ui'
import { ApiError } from '@/lib/api/client'
import { countRunJobs } from '@/lib/api/crawl-jobs'
import { listRunSamples } from '@/lib/api/responses'
import { pageLabel } from '@/lib/l3/samples'
import type { RawResponseSummary } from '@/lib/types'

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
export function SamplesPanel({ runId, ownBrandId }: { runId: number; ownBrandId: number }) {
  const [samples, setSamples] = useState<RawResponseSummary[] | null>(null)
  const [total, setTotal] = useState(0)
  const [failed, setFailed] = useState(0)
  const [offset, setOffset] = useState(0)
  const [error, setError] = useState<Error | null>(null)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let alive = true
    setError(null)
    setSamples(null)
    Promise.all([
      listRunSamples({ runId, limit: PAGE_SIZE, offset }),
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
  }, [runId, offset, attempt])

  if (error) {
    return (
      <ErrorState
        status={error instanceof ApiError ? error.status : 0}
        message={error instanceof ApiError ? error.detail : '加载失败'}
        onRetry={() => setAttempt((a) => a + 1)}
      />
    )
  }

  if (samples === null) {
    return (
      <div style={{ display: 'grid', gap: 8 }}>
        <Skeleton height={20} />
        <Skeleton height={20} />
        <Skeleton height={20} />
      </div>
    )
  }

  if (total === 0) {
    return (
      <EmptyState>
        <strong style={{ color: 'var(--text-secondary)' }}>这次运行没有样本</strong>
        <span>
          {failed > 0
            ? `${failed} 条采样全部失败，一条回答都没拿到 —— 这是采集出了问题，不是 AI 没提你的品牌。可以在任务头点「立即运行」重跑一次。`
            : '还没有采样回来。这次运行可能刚发起，点上面的「刷新」看进度。'}
        </span>
      </EmptyState>
    )
  }

  const label = pageLabel(offset, samples.length, total)

  return (
    <div>
      {failed > 0 ? (
        <PanelNote>
          另有 <strong>{failed}</strong> 条采样失败，没产出回答 ——
          <strong>它们不在下表里</strong>，也不在任何比率的分母里。
          分母少一截时所有比率都会偏高，别拿它和一次完整运行直接比。
        </PanelNote>
      ) : null}

      <SampleTable samples={samples} ownBrandId={ownBrandId} />

      {/* 证据页（A7）还没做，所以行点不进去。这句写出来是为了让
          「点不动」看起来像未完成，而不是像坏了 */}
      <PanelNote>
        单条证据页还没做，所以行暂时点不进去。要看全文用样本 id 调
        <span className="mono"> /v1/responses/&#123;id&#125;</span>。
      </PanelNote>

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
