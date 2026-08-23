import { formatFraction, formatRate, rate } from '@/lib/l3/rates'
import type { BarDatum } from '@/lib/types'

import styles from './traces.module.css'
import { TickScale } from './TickScale'

/**
 * 逐提问的道 —— 一条提问一道。
 *
 * 两处刻意和上一版不同：
 *
 * 1. **提问原文用正文字号，不再是 13px 的右对齐表格行。**
 *    提问是这个产品的**输入变量**，上一版把它排得比它派生出来的百分比还小。
 * 2. **条是刻度尺，不是实心条。** 这一批数据每条提问只采了 3 次 ——
 *    实心条会让 100% 看起来像一个厚实的结论，而它其实是 3/3。
 *    刻度把「只采了三次」直接画出来。
 */
export function TraceBars({ data }: { data: BarDatum[] }) {
  if (data.length === 0) return null

  return (
    <div className={styles.list}>
      {data.map((d) => {
        const r = rate(d.m, d.n)
        return (
          <div key={d.key} className={styles.row}>
            <div className={styles.label} title={d.label}>
              {d.label}
            </div>
            <div className={styles.scaleCell}>
              <TickScale m={d.m} n={d.n} tone={d.own ? 'own' : 'other'} />
            </div>
            <div className={styles.figures}>
              <span
                className={`${styles.rate} mono`}
                data-zero={r === 0 || undefined}
                data-void={r === null || undefined}
              >
                {formatRate(r)}
              </span>
              <span className={`${styles.frac} mono`}>{formatFraction(d.m, d.n)}</span>
            </div>
          </div>
        )
      })}
    </div>
  )
}
