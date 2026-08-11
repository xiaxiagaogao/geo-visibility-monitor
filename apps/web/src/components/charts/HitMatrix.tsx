import type { MatrixCell, MatrixRow } from '@/lib/l3/matrix'
import { formatFraction, formatRate } from '@/lib/l3/rates'

import styles from './charts.module.css'

export interface MatrixColumn {
  brandId: number
  label: string
  own?: boolean
}

/**
 * 命中矩阵 —— 行是提问、列是品牌。
 *
 * 只吃 props，join 在 `lib/l3/matrix` 里做完了（`components/` 不许 fetch）。
 *
 * **格里不显示 `#N`。** 设计稿的「命中 · 有顺位」那一档要的是该品牌在这几次
 * 采样里的**中位出场顺位**，那是个分布；counts 只给得出 `m_first` 这一个计数，
 * 拿它反推名次就是编数据。设计稿本来就允许省掉 `#`，所以这不是缺陷，
 * 是「绝不伪造名次」的落地（API.md §9 最后一行）。
 */
export function HitMatrix({ rows, columns }: { rows: MatrixRow[]; columns: MatrixColumn[] }) {
  return (
    <>
      <div className={styles.matrixScroll}>
        <table className={styles.matrix}>
          <thead>
            <tr>
              <th className={styles.rowHead} />
              {columns.map((c) => (
                <th key={c.brandId} className={c.own ? styles.colOwn : undefined} scope="col">
                  {c.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.promptId}>
                {/* 行首带这一行自己的指标 —— 读矩阵时不用在脑子里除一遍 */}
                <th className={styles.rowHead} scope="row">
                  <div className={styles.rowTitle} title={row.promptText}>
                    {row.promptText}
                  </div>
                  <div
                    className={`${styles.rowMeta} ${row.ownRate === 0 ? styles.rowMetaZero : ''}`}
                  >
                    {formatRate(row.ownRate)}　{formatFraction(row.ownM, row.n)}
                  </div>
                </th>
                {row.cells.map((cell) => (
                  <Cell key={cell.brandId} cell={cell} row={row} columns={columns} />
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Legend />
    </>
  )
}

const LEVEL_CLASS = {
  zero: '',
  l1: styles.l1,
  l2: styles.l2,
  l3: styles.l3,
} as const

function Cell({
  cell,
  row,
  columns,
}: {
  cell: MatrixCell
  row: MatrixRow
  columns: MatrixColumn[]
}) {
  const brand = columns.find((c) => c.brandId === cell.brandId)?.label ?? `#${cell.brandId}`

  // 未命中显示 `0 / 5` 而不是 `—`。
  //
  // 设计稿那一格写的是「虚线空格 —」，这里**刻意没照搬**：`—` 是留给
  // 「算不出」的，把一个真实的 0 写成 `—` 就是纪律 §3.2 明令禁止的美化。
  // 虚线框本身已经是「没被提到」的视觉信号，格里再写 0/5 只是把它说清楚。
  //
  // 反过来 n = 0 那一格才是真的 `—`：这条提问这次一条有效样本都没有，
  // 写 0/0 会让人以为跑了但一次没提到。
  if (cell.kind === 'na') {
    return (
      <td
        className={`${styles.cell} ${styles.zero} ${styles.na}`}
        title={`${brand} · ${row.promptText}：这次没有有效样本，算不出`}
      >
        <div className={styles.cellMain}>—</div>
      </td>
    )
  }

  const tone =
    cell.kind === 'zeroOwn'
      ? `${styles.zero} ${styles.zeroOwn}`
      : cell.kind === 'zero'
        ? styles.zero
        : LEVEL_CLASS[cell.level]

  return (
    <td
      className={`${styles.cell} ${tone}`}
      title={`${brand} · ${row.promptText}：${formatRate(cell.rate)}（${formatFraction(cell.m, cell.n)}）`}
    >
      <div className={styles.cellMain}>{formatFraction(cell.m, cell.n)}</div>
    </td>
  )
}

function Legend() {
  return (
    <div className={styles.legend}>
      <span>
        <span className={styles.swatch} style={{ background: 'var(--seq-1)' }} />
        ≤ 1/3
      </span>
      <span>
        <span className={styles.swatch} style={{ background: 'var(--seq-2)' }} />
        ≤ 2/3
      </span>
      <span>
        <span className={styles.swatch} style={{ background: 'var(--seq-3)' }} />
        &gt; 2/3
      </span>
      <span>
        <span
          className={styles.swatch}
          style={{ border: '1px dashed var(--border-strong)' }}
        />
        未提及（真实的 0）
      </span>
      <span>
        <span className={styles.swatch} style={{ border: '1.5px dashed var(--danger)' }} />
        本品挂零
      </span>
      <span>
        <span
          className={styles.swatch}
          style={{ border: '1px dashed var(--border)', opacity: 0.7 }}
        />
        无有效样本，算不出
      </span>
      <span style={{ marginLeft: 'auto' }}>格内为命中数 / 有效样本数</span>
    </div>
  )
}
