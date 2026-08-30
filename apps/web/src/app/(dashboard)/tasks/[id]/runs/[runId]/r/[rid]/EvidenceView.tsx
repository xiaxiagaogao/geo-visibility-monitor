'use client'

import Link from 'next/link'
import { useEffect, useMemo, useState } from 'react'

import evidence from '@/components/evidence/evidence.module.css'
import { HighlightedText, type Highlight } from '@/components/evidence/HighlightedText'
import {
  Aside,
  Blank,
  Button,
  Fault,
  Mark,
  markTone,
  Pending,
  Plate,
  kit,
  Table,
  type MarkTone,
} from '@/components/kit'
import { brandNameMap, listBrands } from '@/lib/api/brands'
import { ApiError } from '@/lib/api/client'
import { getResponse } from '@/lib/api/responses'
import { getRun, getTask } from '@/lib/api/tasks'
import { buildHighlights, mentionOrder } from '@/lib/l3/evidence'
import { citationState, searchUsedLabel } from '@/lib/l3/search-used'
import type { Citation, Mention, RawResponse, RunDetail, Task } from '@/lib/types'

const STATUS_LABEL: Record<string, string> = {
  ok: '有效',
  empty: '空回答',
  too_short: '太短',
  error: '抓取出错',
}

const STATUS_TONE: Record<string, MarkTone> = {
  ok: 'ok',
  empty: 'warn',
  too_short: 'warn',
  error: 'fault',
}

/**
 * 单条回答证据（A7）。路由 `/tasks/[id]/runs/[runId]/r/[rid]`。
 *
 * 这一页展示的是**记录本身**，不是它的派生数字 —— 所以版式和别处不同：
 * 提问用展示字号（它是输入变量，上一版把它排得比派生出来的百分比还小），
 * 回答原文摊在一块内陷的面上、左边一道竖线、**行宽限死 42 个汉字**
 * （上一版铺满 1140px，一行 80 字，读到行尾找不回行首）。
 *
 * **`runId` 在这一页只用来生成返回链接，不参与任何数字。** 样本本身由 `rid`
 * 唯一确定，`/v1/responses/{id}` 也不回传它属于哪个 run —— 所以这里刻意不
 * 拿 runId 去断言归属，也就不会出现「URL 里的 run 和实际样本对不上、
 * 页面却煞有介事地按那个 run 报数」的情况。竞品名取自该 run 的快照，
 * 万一 runId 真的对不上，取不到的名字会显示成 `#id`，是看得见的降级，
 * 不是悄悄换成另一批名字。
 */
export function EvidenceView({
  taskId,
  runId,
  responseId,
}: {
  taskId: number
  runId: number
  responseId: number
}) {
  const [sample, setSample] = useState<RawResponse | null>(null)
  const [task, setTask] = useState<Task | null>(null)
  const [run, setRun] = useState<RunDetail | null>(null)
  const [brands, setBrands] = useState<Map<number, string>>(new Map())
  const [error, setError] = useState<Error | null>(null)
  const [attempt, setAttempt] = useState(0)
  const [showShot, setShowShot] = useState(false)

  useEffect(() => {
    let alive = true
    setError(null)
    setSample(null)
    Promise.all([getResponse(responseId), getTask(taskId), getRun(runId), listBrands()])
      .then(([s, t, r, b]) => {
        if (!alive) return
        setSample(s)
        setTask(t)
        setRun(r)
        setBrands(brandNameMap(b.items))
      })
      .catch((e: unknown) => {
        if (alive) setError(e instanceof Error ? e : new Error(String(e)))
      })
    return () => {
      alive = false
    }
  }, [responseId, taskId, runId, attempt])

  const ownBrandId = task?.brand_id ?? -1

  const { highlights, mismatches } = useMemo(() => {
    if (!sample) return { highlights: [], mismatches: [] }
    return buildHighlights(sample.full_text, sample.mentions, ownBrandId)
  }, [sample, ownBrandId])

  if (error) {
    return (
      <Fault
        status={error instanceof ApiError ? error.status : 0}
        message={
          error instanceof ApiError && error.status === 404
            ? '没有这条样本，或它不在你的可见范围内'
            : error instanceof ApiError
              ? error.detail
              : '加载失败'
        }
        onRetry={() => setAttempt((a) => a + 1)}
      />
    )
  }

  if (!sample || !task || !run) {
    return (
      <div className={evidence.stack}>
        <Pending height={20} width="50%" />
        <Pending height={92} />
        <Pending height={300} />
      </div>
    )
  }

  // 名字优先取 run 快照（竞品被删之后「当时拿它比过」这个事实仍应留着），
  // 本品取当前品牌表 —— 它不在 run 的竞品快照里
  const nameOf = (brandId: number): string => {
    if (brandId === ownBrandId) return brands.get(brandId) ?? `#${brandId}`
    const snap = run.competitors.find((c) => c.competitor_brand_id === brandId)
    return snap?.brand_name ?? brands.get(brandId) ?? `#${brandId}`
  }

  const status = sample.answer_status ?? ''
  const order = mentionOrder(highlights)
  const search = searchUsedLabel(sample.search_used)

  const marks: Highlight[] = highlights.map((h) => ({
    offset: h.offset,
    matchedTerm: h.matchedTerm,
    className: h.own ? evidence.markOwn : evidence.mark,
    title: `${nameOf(h.brandId)}　命中别名：${h.matchedTerm}`,
  }))

  return (
    <div className={evidence.stack}>
      <div className={evidence.head}>
        {/* 措辞和全站一致：**只写目的地的名字**，不写「回到」——
            箭头已经说了方向。（这一页不套 PageHead：它的头部是一行
            上下文面包屑（任务名 · 样本 # · 平台 · 时间），不是页标题。） */}
        <Link href={`/tasks/${taskId}/runs/${runId}`} className={kit.link}>
          ← 这次运行
        </Link>
        <span className={evidence.headSep}>·</span>
        <span>{task.name}</span>
        <span className={evidence.headSep}>·</span>
        <span>样本 #{sample.id}</span>
        <span className={evidence.headSep}>·</span>
        <span>{sample.platform}</span>
        <span className={evidence.headSep}>·</span>
        <span>{sample.created_at.slice(0, 16).replace('T', ' ')}</span>
        {status ? (
          <Mark tone={STATUS_TONE[status] ?? 'plain'}>{STATUS_LABEL[status] ?? status}</Mark>
        ) : (
          <Mark tone="void">未判定</Mark>
        )}
        {/* P2-37 联网标注。**三态**，判定在 lib/l3/search-used.ts ——
            `null` 走空心虚线而不是实心记号：它是「不知道」，不是一个结论 */}
        <Mark tone={search.degraded ? 'void' : markTone(search.tone)}>{search.text}</Mark>
      </div>

      <Plate>
        <span className={evidence.promptStamp}>提问</span>
        <p className={evidence.prompt}>{sample.prompt_text}</p>
      </Plate>

      {/* 不变量没成立时**必须显示**，不能吞掉。静默画错比空着糟得多：
          用户会拿一段错的原文去跟客户解释结论。 */}
      {mismatches.length > 0 ? (
        <div className={evidence.mismatch} role="alert">
          <strong className={evidence.mismatchLead}>
            有 {mismatches.length} 处标注与原文对不上，已不画高亮。
          </strong>
          <div>
            按 <span className="mono">first_offset</span> 切出来的字面和{' '}
            <span className="mono">matched_term</span> 不一致（API.md §7.1 的不变量）。
            这一定是标注侧的问题，前端不会自己去正文里找一个「看起来对」的位置顶上 ——
            那样页面会显得完全正常，而标出来的已经不是 L1 数过的那一处。
          </div>
          {mismatches.map((m, i) => (
            <div key={i} className={evidence.mismatchRow}>
              {nameOf(m.brandId)} @ {m.offset}：标注「{m.expected}」，原文是「
              {m.actual || '（越过正文末尾）'}」
            </div>
          ))}
        </div>
      ) : null}

      <Plate
        title="回答原文"
        subtitle="高亮位置直接来自 L1 标注的 first_offset，不是前端搜出来的 —— 页面上标的就是计数时数的那一处"
        right={
          sample.screenshot_path ? (
            <Button onClick={() => setShowShot((v) => !v)}>
              {showShot ? '收起截图' : '查看截图'}
            </Button>
          ) : null
        }
      >
        {sample.full_text.trim() === '' ? (
          <Blank lead="这条回答是空的">
            采到了但正文为空（<span className="mono">answer_status</span> ={' '}
            {status || '未判定'}），所以它不进分母。
          </Blank>
        ) : (
          <>
            <div className={evidence.sheet}>
              <HighlightedText
                text={sample.full_text}
                highlights={marks}
                className={evidence.fullText}
              />
            </div>
            <div className={evidence.legend}>
              <span>
                <mark className={evidence.markOwn}>本品</mark> {nameOf(ownBrandId)}
              </span>
              <span>
                <mark className={evidence.mark}>竞品</mark> 统一一种底色
              </span>
              {order.length > 0 ? (
                <span className={evidence.order}>
                  <span className={evidence.orderSep}>出场顺序：</span>
                  {order.map((bid, i) => (
                    <span key={bid}>
                      {i > 0 ? ' › ' : ''}
                      {nameOf(bid)}
                    </span>
                  ))}
                </span>
              ) : null}
            </div>
          </>
        )}

        {showShot && sample.screenshot_path ? (
          <div style={{ marginTop: 'var(--sp-4)' }}>
            {/* screenshot_path 已经是 basename，直接拼即可（API.md §7）。
                响应带 no-store，**不要缓存**；也因此默认不加载，点开才拉。
                用原生 img 而不是 next/image：这张图不过 Next 的优化管线，
                它带 Cookie 鉴权且明确不许缓存。 */}
            <img
              className={evidence.shot}
              src={`/v1/media/screenshots/${sample.screenshot_path}`}
              alt={`样本 #${sample.id} 的采集截图`}
            />
          </div>
        ) : null}
      </Plate>

      <Plate
        title="逐品牌标注"
        subtitle="这条样本上，L1 对每个被监测品牌记了什么。矩阵与读数里的每一个整数都由这些行累加而来"
      >
        <MentionTable mentions={sample.mentions} ownBrandId={ownBrandId} nameOf={nameOf} />
      </Plate>

      <Plate
        title="引用来源"
        subtitle="千问的引用来自 SSE 流，不是页面 —— 页面上那块只有站点图标，一条外链都没有"
        right={
          sample.citations.length > 0 ? (
            <span className="mono" style={{ color: 'var(--text-2)', fontSize: 'var(--fs-label)' }}>
              {sample.citations.length} 条
            </span>
          ) : null
        }
      >
        <CitationList citations={sample.citations} searchUsed={sample.search_used} />
      </Plate>

      <Aside>
        这是 L0 原文，未经改写。上面每一个百分比都能顺着这里的标注回溯到这一条。
      </Aside>
    </div>
  )
}

/* ══════ 引用来源（P2-37）══════ */

/**
 * **「没有引用」有四种完全不同的原因，这里必须分得开。**
 *
 * 最要紧的是别把 `search_used === null`（P2-37 之前的样本，我们不知道）
 * 显示成「没联网」—— 库里躺着 55 条那样的历史样本。判定走
 * `lib/l3/search-used.ts` 的纯函数，组件只管画。
 */
function CitationList({
  citations,
  searchUsed,
}: {
  citations: Citation[]
  searchUsed: boolean | null
}) {
  const state = citationState(citations.length, searchUsed)

  if (state === 'none-no-search') {
    return (
      <Blank lead="这次回答没有检索网页">
        所以没有引用来源 —— <strong>这是结果，不是缺陷</strong>。模型靠自身知识作答，
        该样本照常进分母。
      </Blank>
    )
  }

  if (state === 'unknown') {
    return (
      <Blank lead="这条样本没有记录联网情况">
        它采集于联网标注（P2-37）上线之前，所以「有没有检索网页」是<strong>未知</strong>，
        不是「没有」。此后采的样本都会带这个标注。
      </Blank>
    )
  }

  if (state === 'none-despite-search') {
    // 这条是**我们这边的异常**，不是平台行为 —— 所以用告警而不是空态
    return (
      <div className={evidence.mismatch} role="alert">
        <strong className={evidence.mismatchLead}>标注说联网了，却一条引用都没抽到。</strong>
        <div>
          这两件事对不上，多半是流解析出了问题或平台改了结构 ——
          <strong>不要当成「这次没引用」</strong>。请查采集端{' '}
          <span className="mono">qianwen_sse</span> 的解析。
        </div>
      </div>
    )
  }

  return (
    <ol className={evidence.cites}>
      {citations.map((c) => (
        <li key={c.id} className={evidence.cite}>
          <a
            href={c.url}
            target="_blank"
            rel="noopener noreferrer nofollow"
            className={evidence.citeTitle}
          >
            {c.title ?? c.url}
          </a>
          {/* 域名单独显示：GEO 分析真正关心的是「哪些站被引用」，
              而标题会随媒体改版变，域名不会 */}
          <div className={evidence.citeMeta}>
            <span>{c.domain}</span>
            {c.cite_index !== null ? (
              <span className={evidence.citeIndex}>#{c.cite_index}</span>
            ) : null}
          </div>
          {c.snippet ? <p className={evidence.citeSnippet}>{c.snippet}</p> : null}
        </li>
      ))}
    </ol>
  )
}

/* ══════ 逐品牌标注 ══════ */

function MentionTable({
  mentions,
  ownBrandId,
  nameOf,
}: {
  mentions: Mention[]
  ownBrandId: number
  nameOf: (brandId: number) => string
}) {
  if (mentions.length === 0) {
    return (
      <Blank lead="这条样本还没跑过 L1 标注">
        不是「没有品牌被提到」—— 是还不知道。它会落进 n_unannotated。
      </Blank>
    )
  }

  // 本品排第一，其余按出场顺位（没有顺位的排最后）
  const rows = [...mentions].sort((a, b) => {
    if (a.brand_id === ownBrandId) return -1
    if (b.brand_id === ownBrandId) return 1
    return (a.position_rank ?? Infinity) - (b.position_rank ?? Infinity)
  })

  return (
    <Table>
      <thead>
        <tr>
          <th>品牌</th>
          <th>命中方式</th>
          <th>出场顺位</th>
          <th>篇幅位置</th>
          <th>命中别名</th>
          <th>原文片段</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((m) => (
          <tr key={m.id}>
            <td>
              {nameOf(m.brand_id)}
              {m.brand_id === ownBrandId ? (
                <span style={{ marginLeft: 8 }}>
                  <Mark tone="own">本品</Mark>
                </span>
              ) : null}
            </td>
            <td>
              {!m.mentioned ? (
                <Mark>未提及</Mark>
              ) : m.mention_type === 'citation_only' ? (
                <Mark tone="warn">仅引用</Mark>
              ) : (
                <Mark tone="ok">正文命中</Mark>
              )}
            </td>
            <td className="mono">
              {/* citation_only 是 null，不是排最后 —— 正文里没出现就没有「出场位置」 */}
              {m.position_rank === null ? '—' : `#${m.position_rank}`}
            </td>
            <td className={evidence.metaCell}>{m.position_bucket ?? '—'}</td>
            <td className="mono">{m.matched_term ?? '—'}</td>
            <td className={evidence.snippetCell}>{m.evidence_snippet ?? '—'}</td>
          </tr>
        ))}
      </tbody>
    </Table>
  )
}
