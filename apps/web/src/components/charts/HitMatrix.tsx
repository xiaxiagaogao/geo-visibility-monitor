'use client'

import { BRAND_NAMES, type MatrixRow, OWN_BRAND_ID, PROMPT_BY_ID } from '@/lib/fixtures'
import { formatRate, matrixLevel, rate } from '@/lib/l3/rates'

import styles from './charts.module.css'

const LEVEL_CLASS = {
  zero: styles.zero,
  l1: styles.l1,
  l2: styles.l2,
  l3: styles.l3,
} as const

/**
 * 提问 × 品牌命中矩阵 —— 采纳竞品的下钻交互（docs/27 §4 决定 ⑤）。
 *
 * 与竞品的差别：它的列是**平台**（一个品牌跑四个平台），
 * 我们的列是**品牌**（八个品牌跑一个平台）—— 因为我们只接了 DeepSeek。
 * 结构同构，等第二个 Provider 上线时再决定要不要加一层。
 *
 * 行首挂该行自己的指标（学自竞品）：读矩阵时不用在脑子里除一遍。
 */
export function HitMatrix({
  rows,
  columns,
  onPick,
}: {
  rows: MatrixRow[]
  columns: number[]
  onPick?: (promptId: number, brandId: number) => void
}) {
  return (
    <>
      <div className={styles.matrixScroll}>
        <table className={styles.matrix}>
          <thead>
            <tr>
              <th />
              {columns.map((id) => (
                <th key={id} className={id === OWN_BRAND_ID ? styles.colOwn : undefined}>
                  {BRAND_NAMES[id]}
                  {id === OWN_BRAND_ID ? '（本品）' : ''}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const ownM = row.cells.find((c) => c.brandId === OWN_BRAND_ID)?.m ?? 0
              const ownRate = rate(ownM, row.n)
              const ownZero = ownRate === 0

              return (
                <tr key={row.promptId}>
                  <th scope="row" className={styles.rowHead}>
                    <div className={styles.rowTitle}>
                      {PROMPT_BY_ID.get(row.promptId)?.text ?? `#${row.promptId}`}
                    </div>
                    <div className={`${styles.rowMeta} ${ownZero ? styles.rowMetaZero : ''}`}>
                      本品 {formatRate(ownRate)} · {ownM}/{row.n}
                    </div>
                  </th>

                  {columns.map((brandId) => {
                    const cell = row.cells.find((c) => c.brandId === brandId)
                    const m = cell?.m
                    const hit = m !== null && m !== undefined
                    const r = hit ? rate(m, row.n) : null
                    const level = matrixLevel(r)
                    const isOwn = brandId === OWN_BRAND_ID

                    const cls = [
                      styles.cell,
                      LEVEL_CLASS[level],
                      level === 'zero' && isOwn ? styles.zeroOwn : '',
                      hit ? styles.cellHit : '',
                    ]
                      .filter(Boolean)
                      .join(' ')

                    const label = `${PROMPT_BY_ID.get(row.promptId)?.text ?? row.promptId} · ${
                      BRAND_NAMES[brandId]
                    } · ${hit ? `${m}/${row.n}` : '未提及'}`

                    return (
                      <td key={brandId} className={cls}>
                        {hit && onPick ? (
                          <button
                            type="button"
                            className={styles.cellButton}
                            aria-label={label}
                            onClick={() => onPick(row.promptId, brandId)}
                          >
                            {m}/{row.n}
                          </button>
                        ) : (
                          <span aria-label={label}>{hit ? `${m}/${row.n}` : '—'}</span>
                        )}
                      </td>
                    )
                  })}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <div className={styles.legend}>
        <span>
          <i className={styles.legendSwatch} style={{ border: '1px solid var(--border)' }} />
          未提及
        </span>
        <span>
          <i className={styles.legendSwatch} style={{ background: 'var(--seq-1)' }} />≤33%
        </span>
        <span>
          <i className={styles.legendSwatch} style={{ background: 'var(--seq-2)' }} />
          34–66%
        </span>
        <span>
          <i className={styles.legendSwatch} style={{ background: 'var(--seq-3)' }} />≥67%
        </span>
        <span>
          <i className={styles.legendSwatch} style={{ border: '1.4px solid var(--bad)' }} />
          本品挂零
        </span>
      </div>
    </>
  )
}
