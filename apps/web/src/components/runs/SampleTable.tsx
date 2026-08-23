import Link from 'next/link'

import { Badge, Degraded, Table, ui, type BadgeTone } from '@/components/ui'
import { isPreviewTruncated, ownHit, type SampleHitKind } from '@/lib/l3/samples'
import { searchUsedLabel } from '@/lib/l3/search-used'
import type { RawResponseSummary } from '@/lib/types'

import styles from './runs.module.css'

/** `answer_status` 的人话。**null 是「还没判定」，不是「有效」** */
const STATUS_LABEL: Record<string, string> = {
  ok: '有效',
  empty: '空回答',
  too_short: '太短',
  error: '抓取出错',
}

const STATUS_TONE: Record<string, BadgeTone> = {
  ok: 'ok',
  empty: 'warning',
  too_short: 'warning',
  error: 'danger',
}

const HIT_LABEL: Record<SampleHitKind, string> = {
  body: '正文命中',
  citationOnly: '仅引用',
  none: '未提及',
  unannotated: '未标注',
}

const HIT_TONE: Record<SampleHitKind, BadgeTone> = {
  body: 'ok',
  citationOnly: 'warning',
  // 「未提及」是真实结论，不是错误 —— 不染红。红色留给「本该有却没有」
  none: 'neutral',
  unannotated: 'neutral',
}

/**
 * 某次运行的样本表。只吃 props，不 fetch（取数在 SamplesPanel）。
 *
 * 第一列的样本 id 链到证据页 `/tasks/[id]/runs/[runId]/r/[rid]`（A7）。
 * **链的是 id 这一列，不是整行**：整行可点的话，选中一段预览文字
 * 松开鼠标就会跳走 —— 而这张表里的预览正是用来扫读的。
 */
export function SampleTable({
  samples,
  ownBrandId,
  taskId,
  runId,
}: {
  samples: RawResponseSummary[]
  /** 本品 —— 命中必须按 brand_id 关联，不许拿 mentions[0] */
  ownBrandId: number
  taskId: number
  runId: number
}) {
  return (
    <Table>
      <thead>
        <tr>
          <th>样本</th>
          <th>提问</th>
          <th>平台</th>
          <th>回答</th>
          <th>联网</th>
          <th>本品</th>
          <th>命中处</th>
        </tr>
      </thead>
      <tbody>
        {samples.map((s) => {
          const hit = ownHit(s, ownBrandId)
          const status = s.answer_status ?? ''
          return (
            <tr key={s.id}>
              <td className={ui.numeric}>
                <Link href={`/tasks/${taskId}/runs/${runId}/r/${s.id}`} className={ui.rowLink}>
                  #{s.id}
                </Link>
              </td>

              <td>
                <div className={styles.samplePrompt}>{s.prompt_text}</div>
                {/* 预览只有前 160 字，截断了就明说 —— 省略号是「还有」，
                    不加的话用户会以为 AI 的回答就这么短 */}
                <div className={styles.samplePreview}>
                  {s.text_preview}
                  {isPreviewTruncated(s) ? '…' : ''}
                </div>
              </td>

              <td style={{ color: 'var(--text-secondary)', fontSize: 'var(--fs-xs)' }}>
                {s.platform}
              </td>

              <td>
                {status ? (
                  <Badge tone={STATUS_TONE[status] ?? 'neutral'}>
                    {STATUS_LABEL[status] ?? status}
                  </Badge>
                ) : (
                  <Degraded>未判定</Degraded>
                )}
                {/* 不可用的样本不进分母，这句必须写在行上：
                    否则用户会拿「表里 35 行」去对「有效样本 31」，以为哪边算错了 */}
                {status && status !== 'ok' ? (
                  <div className={styles.sampleNote}>不进分母</div>
                ) : null}
              </td>

              {/* P2-37 联网标注。三态判定在 lib/l3/search-used.ts ——
                  `null` 走 Degraded：它是「不知道」，不是「没联网」 */}
              <td>
                {(() => {
                  const label = searchUsedLabel(s.search_used)
                  return label.degraded ? (
                    <Degraded>未记录</Degraded>
                  ) : (
                    <Badge tone={label.tone}>{label.text}</Badge>
                  )
                })()}
              </td>

              <td>
                {hit.kind === 'unannotated' ? (
                  // 降级态 ≠ 空态：「还没标注」不是「AI 没提你」
                  <Degraded>未标注</Degraded>
                ) : (
                  <Badge tone={HIT_TONE[hit.kind]}>{HIT_LABEL[hit.kind]}</Badge>
                )}
                {hit.rank !== null ? (
                  <span
                    className={`${ui.numeric} ${styles.sampleRank}`}
                    title="出场顺位：在被监测品牌里第几个出现。是位置事实，不是「AI 首推」"
                  >
                    #{hit.rank}
                  </span>
                ) : null}
              </td>

              <td className={styles.sampleSnippet}>{hit.snippet ?? '—'}</td>
            </tr>
          )
        })}
      </tbody>
    </Table>
  )
}
