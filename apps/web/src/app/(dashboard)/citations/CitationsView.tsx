'use client'

import { useCallback, useEffect, useState } from 'react'

import {
  Aside,
  Blank,
  Fault,
  Gloss,
  Mark,
  Notation,
  Pending,
  PageHead,
  Plate,
  Select,
  TickScale,
} from '@/components/kit'
import { brandNameMap, listBrands } from '@/lib/api/brands'
import { fetchCitationDomains } from '@/lib/api/citations'
import { ApiError } from '@/lib/api/client'
import { fetchBrandCounts } from '@/lib/api/counts'
import { listTasks } from '@/lib/api/tasks'
import {
  citationCoverage,
  citationRows,
  citationScaleMax,
  type CitationRow,
} from '@/lib/l3/citations'
import { formatFraction, formatRate, rate } from '@/lib/l3/rates'
import type { CitationDomainsResult, CountsResponse } from '@/lib/types'

import styles from './citations.module.css'

/** 榜单取多少行。后端上限 200；这里要的是「看得完的一屏」，不是全量导出。 */
const TOP_N = 25

/**
 * 引用榜。
 *
 * 口径是**跨这个品牌的全部 run 累计**，不钉在某一次运行上 ——
 * 「哪些站正在被 AI 引用」是个累计问题（`fetchBrandCounts` 的注释里
 * 写了为什么它和 `fetchRunCounts` 是两个函数而不是一个可选参数）。
 *
 * 页面上有两块，回答两个不同的问题：
 *   1. **联网分桶** —— 我们对「这批回答有没有检索网页」到底知道多少？
 *   2. **域名榜** —— AI 在照着谁的网页说话？
 *
 * 第一块排在第二块前面是有理由的：实测数据里 180 条有效样本中有 161 条
 * 的联网状态是 `unknown`。**先说清楚这件事**，读者才不会把下面那张榜
 * 当成「AI 引用行为的全貌」。
 */
export function CitationsView() {
  const [monitored, setMonitored] = useState<{ id: number; name: string }[] | null>(null)
  const [brandId, setBrandId] = useState<number | null>(null)
  const [domains, setDomains] = useState<CitationDomainsResult | null>(null)
  const [buckets, setBuckets] = useState<CountsResponse | null>(null)
  const [error, setError] = useState<Error | null>(null)
  const [attempt, setAttempt] = useState(0)

  // **只列有任务的品牌。**
  //
  // `/v1/brands` 返回的是全部品牌，其中绝大多数是**竞品** —— 它们作为对照
  // 存在于快照里，但没有人为它们跑任务，所以永远不会有引用。
  // 直接拿 brands[0] 当默认值，一进页面就落在一个竞品上、满屏空态；
  // 而下拉里 17 个选项有 16 个点进去是空的。
  //
  // 「有任务」不是审美判断，是事实：引用榜是按**被监测品牌**看的。
  useEffect(() => {
    let alive = true
    Promise.all([listTasks(), listBrands()])
      .then(([t, b]) => {
        if (!alive) return
        const names = brandNameMap(b.items)
        const seen = new Set<number>()
        const list: { id: number; name: string }[] = []
        for (const task of t.items) {
          if (seen.has(task.brand_id)) continue
          seen.add(task.brand_id)
          list.push({ id: task.brand_id, name: names.get(task.brand_id) ?? `#${task.brand_id}` })
        }
        setMonitored(list)
        setBrandId((cur) => cur ?? list[0]?.id ?? null)
      })
      .catch((e: unknown) => {
        if (alive) setError(e instanceof Error ? e : new Error(String(e)))
      })
    return () => {
      alive = false
    }
  }, [])

  const load = useCallback(() => setAttempt((a) => a + 1), [])

  useEffect(() => {
    if (brandId === null) return
    let alive = true
    setError(null)
    setDomains(null)
    setBuckets(null)
    Promise.all([
      fetchCitationDomains({ brandId, limit: TOP_N }),
      fetchBrandCounts({ brandId, groupBy: 'search_used' }),
    ])
      .then(([d, b]) => {
        if (!alive) return
        setDomains(d)
        setBuckets(b)
      })
      .catch((e: unknown) => {
        if (alive) setError(e instanceof Error ? e : new Error(String(e)))
      })
    return () => {
      alive = false
    }
  }, [brandId, attempt])

  const brandName = monitored?.find((b) => b.id === brandId)?.name ?? ''

  return (
    <div className={styles.stack}>
      <PageHead
        title="引用榜"
        lede={
          <>
            AI 回答里被引用的网页来自哪些站。数据来自千问的 <span className="mono">SSE</span> 流
            —— <strong>它的引用不在页面上</strong>，页面那块只有站点图标、一条外链都没有。
            口径是这个品牌<strong>全部运行的累计</strong>，不是某一次。
          </>
        }
        action={
          monitored && monitored.length > 1 ? (
            <Select
              value={brandId ?? ''}
              onChange={(e) => setBrandId(Number(e.target.value))}
              aria-label="选择被监测品牌"
            >
              {monitored.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name}
                </option>
              ))}
            </Select>
          ) : null
        }
      />

      {monitored !== null && monitored.length === 0 ? (
        <Plate>
          <Blank lead="还没有被监测的品牌">
            引用榜是按被监测品牌看的。先在「检测任务」里建一个任务，
            跑过一次之后这里就会有数据。
          </Blank>
        </Plate>
      ) : error ? (
        <Fault
          status={error instanceof ApiError ? error.status : 0}
          message={error instanceof ApiError ? error.detail : '加载失败'}
          onRetry={load}
        />
      ) : (
        <>
          <SearchBuckets counts={buckets} />
          <DomainBoard result={domains} brandName={brandName} />
        </>
      )}
    </div>
  )
}

/* ══════════════════════════════════════════════════════════════════
   联网分桶
   ══════════════════════════════════════════════════════════════════ */

/** 三态**全部列出**，包括后端没返回的那一档 —— 见下面的注释 */
const BUCKETS: { key: string; label: string; gloss: string; void?: boolean }[] = [
  {
    key: 'true',
    label: '已联网',
    gloss: '这次回答检索了网页来源 —— 引用榜上的数据全部来自这一档',
  },
  {
    key: 'false',
    label: '未联网',
    gloss: '确认没有检索网页，靠模型自身知识作答。这是结果，不是废样本',
  },
  {
    key: 'unknown',
    label: '未记录',
    gloss: '采集时还没有联网标注（P2-37 之前）—— 是「不知道」，不是「没有」',
    void: true,
  },
]

function SearchBuckets({ counts }: { counts: CountsResponse | null }) {
  if (counts === null) {
    return (
      <Plate title="这批样本，我们知道多少">
        <Pending height={92} />
      </Plate>
    )
  }

  const total = counts.denominator.n_valid
  const byKey = new Map(counts.series.map((s) => [s.key, s.denominator.n_valid]))
  const unknown = byKey.get('unknown') ?? 0
  const unknownShare = rate(unknown, total)

  return (
    <Plate
      title="这批样本，我们知道多少"
      subtitle="下面那张榜只可能来自「已联网」那一档。所以得先说清楚它占多大比例。"
    >
      <div className={styles.buckets}>
        {BUCKETS.map((b) => {
          const n = byKey.get(b.key) ?? 0
          // **后端不返回空桶，但这三档必须都画出来。**
          // 少画一档，读者会以为这批数据里只有另外两种可能；
          // 而「一条确认未联网的样本都没有」本身就是一条结论。
          const absent = !byKey.has(b.key)
          return (
            <div key={b.key} className={styles.bucket} data-void={b.void || undefined}>
              <div className={styles.bucketLabel}>
                {b.label}
                <Gloss text={b.gloss} />
              </div>
              <div className={styles.bucketValue}>
                <span className="mono">{formatRate(rate(n, total))}</span>
              </div>
              <TickScale m={n} n={total} tone={b.void ? 'other' : 'own'} zeroMark={false} />
              <div className={`${styles.bucketDenom} mono`}>{formatFraction(n, total)}</div>
              {absent ? (
                <div className={styles.bucketAbsent}>后端一条都没返回 —— 这一档是空的</div>
              ) : null}
            </div>
          )
        })}
      </div>

      {/* 这是这批数据最该被说出来的一句话 */}
      {unknownShare !== null && unknownShare > 0.5 ? (
        <div style={{ marginTop: 'var(--sp-4)' }}>
          <Aside tone="alert">
            <strong>{formatRate(unknownShare)}</strong> 的有效样本（{formatFraction(unknown, total)}
            ）<strong>没有联网记录</strong>。它们采集于联网标注上线之前 ——
            这是「不知道」，<strong>不是「没联网」</strong>。
            把这一档并进「未联网」去算占比，就是在报告里断言一件我们没测过的事。
          </Aside>
        </div>
      ) : null}
    </Plate>
  )
}

/* ══════════════════════════════════════════════════════════════════
   域名榜
   ══════════════════════════════════════════════════════════════════ */

function DomainBoard({
  result,
  brandName,
}: {
  result: CitationDomainsResult | null
  brandName: string
}) {
  if (result === null) {
    return (
      <Plate title="被引用的站">
        <div style={{ display: 'grid', gap: 8 }}>
          <Pending height={24} />
          <Pending height={24} />
          <Pending height={24} />
        </div>
      </Plate>
    )
  }

  const rows = citationRows(result)
  const cov = citationCoverage(result)
  const max = citationScaleMax(rows)

  if (rows.length === 0) {
    return (
      <Plate title="被引用的站">
        <Blank lead={`${brandName || '这个品牌'}还没有抽到任何引用`}>
          要么这批样本一次都没有检索网页，要么它们采集于引用抽取上线之前。
          这不是「AI 没有引用来源」—— 是我们这边还没有记录。
        </Blank>
      </Plate>
    )
  }

  return (
    <Plate
      title="被引用的站"
      subtitle="AI 在照着谁的网页说话。按引用次数排 —— 但只看次数会读错，见每行右边的样本数。"
      right={
        <span className={`${styles.headline} mono`}>
          {cov.total} 次 · {cov.domains} 个域名
        </span>
      }
    >
      {/* API.md §4 明确警告过的坑：n_citations 描述的是全集，不是 items 那几行。
          带 limit 时 Σitems < 全集是正常的 —— 别拿 items 的和当分母。 */}
      {cov.truncated ? (
        <div style={{ marginBottom: 'var(--sp-4)' }}>
          <Aside>
            下面是前 {rows.length} 个域名，占 <strong>{cov.listed}</strong> 次引用；
            全集是 <strong>{cov.total}</strong> 次、{cov.domains} 个域名。
            <strong>别拿这几行的和当分母。</strong>
          </Aside>
        </div>
      ) : null}

      <div className={styles.board}>
        {rows.map((r) => (
          <DomainRow key={r.domain} row={r} max={max} />
        ))}
      </div>

      <Notation
        entries={[
          { swatch: 'var(--accent)', label: '引用次数' },
          { swatch: 'zero', label: '集中引用：平均每条样本引它 2 次以上' },
        ]}
        note="口径：一个域名在一条回答里被引 3 次就计 3"
      />

      <div style={{ marginTop: 'var(--sp-4)' }}>
        <Aside>
          <strong>只比次数会读错。</strong>「样本数」是一个域名被多少条<em>不同的</em>回答引用过。
          次数高但样本数低，说明是同一批回答在反复引它；次数相近而样本数高的那个，
          覆盖面其实更广 —— 对「该去哪些站铺内容」这个问题，后者更值得看。
        </Aside>
      </div>
    </Plate>
  )
}

function DomainRow({ row, max }: { row: CitationRow; max: number }) {
  const width = max > 0 ? (row.n_citations / max) * 100 : 0
  return (
    <div className={styles.row}>
      <span className={`${styles.rank} mono`}>{row.rank}</span>

      <span className={styles.domain} title={row.domain}>
        {row.domain}
      </span>

      <span className={styles.barCell}>
        <span className={styles.bar} style={{ width: `${width}%` }} />
      </span>

      <span className={`${styles.count} mono`}>{row.n_citations}</span>

      <span className={styles.samples}>
        <span className="mono">{row.n_samples}</span>
        <span className={styles.samplesUnit}>条样本</span>
      </span>

      <span className={styles.flagCell}>
        {row.concentrated ? (
          <Mark tone="warn" >
            集中 ×{row.perSample === null ? '—' : row.perSample.toFixed(1)}
          </Mark>
        ) : null}
      </span>
    </div>
  )
}
