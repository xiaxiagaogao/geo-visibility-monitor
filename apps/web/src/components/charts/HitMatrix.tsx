'use client'

import { type MatrixRow, OWN_BRAND_ID } from '@/lib/fixtures'
import { formatRate, matrixLevel, rate } from '@/lib/l3/rates'
import { brandName, promptText } from '@/lib/selectors'

import styles from './charts.module.css'

const LEVEL_CLASS = {
  zero: styles.zero,
  l1: styles.l1,
  l2: styles.l2,
  l3: styles.l3,
} as const

/**
 * 提问 × 品牌 命中矩阵。
 *
 * 与 GeoMonitor 的差别：它的列是**平台**（一个品牌跑六个平台），
 * 我们的列是**品牌**（八个品牌跑一个平台）—— 因为只接了 DeepSeek。
 * 结构同构，等第二个 Provider 上线再决定要不要加一层。
 *
 * 格子四态：
 *   命中·有顺位 → `3/3` + `#2`   命中·无顺位 → `3/3`
 *   未提及 → 虚线空格            本品挂零 → 虚线 + danger 描边
 *
 * 「绝不伪造名次」是 GeoMonitor 的原则，照搬：`position_rank` 固定数据里还没填，
 * 那就一个 `#` 都不显示，而不是拿别的数糊上去。
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
                  {brandName(id)}
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
                    <div className={styles.rowTitle} title={promptText(row.promptId)}>
                      {promptText(row.promptId)}
                    </div>
                    <div className={`${styles.rowMeta} ${ownZero ? styles.rowMetaZero : ''}`}>
                      本品 {formatRate(ownRate)} · {ownM}/{row.n}
                    </div>
                  </th>

                  {columns.map((brandId) => (
                    <Cell
                      key={brandId}
                      m={row.cells.find((c) => c.brandId === brandId)?.m ?? null}
                      n={row.n}
                      isOwn={brandId === OWN_BRAND_ID}
                      label={`${promptText(row.promptId)} · ${brandName(brandId)}`}
                      onPick={onPick ? () => onPick(row.promptId, brandId) : undefined}
                    />
                  ))}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <div className={styles.legend}>
        <span>
          <i className={styles.swatch} style={{ border: '1px dashed var(--border-strong)' }} />
          未提及
        </span>
        <span>
          <i className={styles.swatch} style={{ background: 'var(--seq-1)' }} />≤33%
        </span>
        <span>
          <i className={styles.swatch} style={{ background: 'var(--seq-2)' }} />
          34–66%
        </span>
        <span>
          <i className={styles.swatch} style={{ background: 'var(--seq-3)' }} />≥67%
        </span>
        <span>
          <i className={styles.swatch} style={{ border: '1.5px dashed var(--danger)' }} />
          本品挂零
        </span>
      </div>
    </>
  )
}

function Cell({
  m,
  n,
  isOwn,
  label,
  rank,
  onPick,
}: {
  m: number | null
  n: number
  isOwn: boolean
  label: string
  /** 出场顺位。后端已有该字段（API.md §7），固定数据没填，故恒为 undefined */
  rank?: number
  onPick?: () => void
}) {
  const hit = m !== null && m > 0
  const r = m === null ? null : rate(m, n)
  const level = matrixLevel(r)
  const zeroOwn = level === 'zero' && isOwn

  const cls = [
    styles.cell,
    LEVEL_CLASS[level],
    zeroOwn ? styles.zeroOwn : '',
    hit && onPick ? styles.hit : '',
  ]
    .filter(Boolean)
    .join(' ')

  const a11y = `${label} · ${m === null || m === 0 ? '未提及' : `${m}/${n}`}`

  const inner = (
    <>
      <span className={styles.cellMain}>{m === null || m === 0 ? '—' : `${m}/${n}`}</span>
      {rank !== undefined ? <span className={styles.cellRank}>#{rank}</span> : null}
    </>
  )

  return (
    <td className={cls}>
      {hit && onPick ? (
        <button type="button" className={styles.cellBtn} aria-label={a11y} onClick={onPick}>
          {inner}
        </button>
      ) : (
        <span className={styles.cellBtn} aria-label={a11y}>
          {inner}
        </span>
      )}
    </td>
  )
}
