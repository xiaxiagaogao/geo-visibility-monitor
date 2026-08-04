'use client'

import { useEffect } from 'react'

import { Badge, Table, tableStyles } from '@/components/ui'
import { BRAND_NAMES, OWN_BRAND_ID } from '@/lib/fixtures'
import type { RawResponse } from '@/lib/types'

import styles from './evidence.module.css'
import { HighlightedText } from './HighlightedText'

const BUCKET_LABEL: Record<string, string> = { head: 'head', middle: 'middle', tail: 'tail' }

/**
 * 证据模态。形态学自竞品：把一次抓取还原成**聊天记录**（提问在右、回答在左），
 * 再往下依次是 L1 命中表、引用来源、证据截图。
 *
 * 比一段掐头去尾的 40 字 snippet 可审计得多 —— 读者能自己判断
 * 「这个品牌到底是被推荐了，还是只是被顺口提了一句」。
 */
export function EvidenceModal({
  response,
  notice,
  onClose,
}: {
  response: RawResponse
  /** 当展示的样本并非用户点中的那一格时，必须说清楚 —— 不许让人以为看到的是真的 */
  notice?: string
  onClose: () => void
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  const hits = response.mentions.filter((m) => m.mentioned)

  return (
    <div className={tableStyles.overlay} onClick={onClose} role="presentation">
      <div
        className={tableStyles.modal}
        role="dialog"
        aria-modal="true"
        aria-label={`回答 #${response.id} 的证据`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className={tableStyles.modalHead}>
          <span className={tableStyles.modalTitle}>
            回答 #{response.id} · {response.platform}
          </span>
          <Badge tone={response.answer_status === 'ok' ? 'ok' : 'bad'}>
            answer_status {response.answer_status}
          </Badge>
          <span style={{ flex: 1 }} />
          <button className={tableStyles.modalClose} onClick={onClose} aria-label="关闭">
            ×
          </button>
        </div>

        <div className={tableStyles.modalBody}>
          {notice ? <p className={styles.notice}>{notice}</p> : null}

          <div className={styles.meta}>
            <span>
              时间 <span className={styles.metaValue}>{response.created_at.slice(0, 16).replace('T', ' ')}</span>
            </span>
            <span>
              任务 <span className={styles.metaValue}>#{response.job_id}</span>
            </span>
            <span>
              耗时 <span className={styles.metaValue}>{response.latency_ms ?? '—'} ms</span>
            </span>
            <span>
              标注 <span className={styles.metaValue}>{response.annotator_version ?? '—'}</span>
            </span>
          </div>

          <div className={`${styles.turn} ${styles.turnAsk}`}>
            <div className={styles.ask}>{response.prompt_text}</div>
          </div>
          <div className={styles.turn}>
            <HighlightedText text={response.full_text} highlights={[]} />
          </div>

          <p className={styles.pending}>
            命中位置内联高亮尚未开启：后端 <code>mentions</code> 表还没有 offset 字段，
            前端不会自己去正文里重找品牌名 —— 那会和 L1 标注口径分叉。
          </p>

          <p className={styles.sectionLabel}>L1 标注 · 命中品牌（{hits.length}）</p>
          <Table>
            <thead>
              <tr>
                <th>品牌</th>
                <th>类型</th>
                <th>首次位置</th>
              </tr>
            </thead>
            <tbody>
              {hits.map((m) => (
                <tr key={m.id}>
                  <td className={m.brand_id === OWN_BRAND_ID ? styles.ownCell : undefined}>
                    {BRAND_NAMES[m.brand_id] ?? `#${m.brand_id}`}
                    {m.brand_id === OWN_BRAND_ID ? '（本品）' : ''}
                  </td>
                  <td>{m.mention_type}</td>
                  <td>
                    <Badge>{m.position_bucket ? BUCKET_LABEL[m.position_bucket] : '—'}</Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </Table>

          <p className={styles.sectionLabel}>引用来源（{response.citations.length}）</p>
          {response.citations.length === 0 ? (
            <p className={styles.footnote}>本样本无解析到引用。</p>
          ) : (
            <ol>
              {response.citations.map((c) => (
                <li key={c.id}>
                  {c.title ?? c.url} · {c.domain}
                </li>
              ))}
            </ol>
          )}

          <p className={styles.sectionLabel}>证据截图</p>
          <div className={styles.shot}>完整回答区域截图（隐藏侧栏）· 点击放大</div>
          <p className={styles.footnote}>不保留 DeepSeek 对话 URL · 会话抓完即删</p>
        </div>
      </div>
    </div>
  )
}
