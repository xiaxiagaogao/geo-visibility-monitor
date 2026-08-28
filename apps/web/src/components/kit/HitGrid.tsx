import type { MatrixRow } from '@/lib/l3/matrix'
import { formatFraction } from '@/lib/l3/rates'

import styles from './traces.module.css'
import { TickScale } from './TickScale'

export interface GridColumn {
  brandId: number
  label: string
  own?: boolean
}

/**
 * 命中矩阵 —— 行是提问、列是品牌。
 *
 * **格里不再是一个填了色的方块。** 上一版每格是一个色阶实心块、数值印在块上，
 * 撞上一个实测出来的死区：三档色阶的中段，白字 3.92:1、深墨字 3.93:1，
 * **两边都够不到 4.5**（详见 tokens.css 文件头 ②）。而且当 n 全是 3 的时候，
 * 8 列深色块看起来像一面很有把握的墙 —— 它其实是 3/3。
 *
 * 现在每格是一小段刻度 + 一个 ink-on-sheet 的 `m/n`（15.4:1）。
 * 数值永远读得清，而「只采了三次」这件事自己会说话。
 *
 * 四态仍然分得开（口径在 `lib/l3/matrix`，这里只管画）：
 *   hit      有命中 —— 刻度上墨
 *   zero     真的是 0 —— 刻度全空
 *   zeroOwn  **本品**挂零 —— 全空 + 第一格描红 + 整格描红框
 *   na       一条有效样本都没有 —— 一格都不画，只留虚线
 */
export function HitGrid({ rows, columns }: { rows: MatrixRow[]; columns: GridColumn[] }) {
  if (rows.length === 0) return null

  return (
    <div className={styles.gridScroll}>
      <table className={styles.grid}>
        <thead>
          <tr>
            <th className={styles.gridCorner} scope="col">
              提问
            </th>
            {columns.map((c) => (
              <th
                key={c.brandId}
                scope="col"
                className={`${styles.gridHead} ${c.own ? styles.gridHeadOwn : ''}`}
              >
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.promptId}>
              <th scope="row" className={styles.gridRowHead}>
                <span className={styles.gridPrompt}>{row.promptText}</span>
                <span className={`${styles.gridRowMeta} mono`}>
                  n = {row.n}
                </span>
              </th>
              {row.cells.map((cell) => (
                <td
                  key={cell.brandId}
                  className={styles.gridCell}
                  data-kind={cell.kind}
                  title={`${formatFraction(cell.m, cell.n)}`}
                >
                  {/* 红色只留给**本品挂零**。竞品这条没出现是常态，不是结论 ——
                      每个 0/3 都描红的话，一屏几十处红色就什么都不说明了。 */}
                  <TickScale
                    m={cell.m}
                    n={cell.n}
                    size="sm"
                    tone={cell.brandId === columns[0]?.brandId ? 'own' : 'other'}
                    zeroMark={cell.kind === 'zeroOwn'}
                  />
                  <span className={`${styles.gridValue} mono`}>
                    {cell.kind === 'na' ? '—' : formatFraction(cell.m, cell.n)}
                  </span>
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
