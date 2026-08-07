import { formatFraction, formatRate, rate } from '@/lib/l3/rates'
import type { BarDatum } from '@/lib/types'

import styles from './charts.module.css'

/**
 * emphasis 横条 —— 本品用主色，其余统一灰。
 *
 * 八个品牌不需要八种颜色：读者只关心「我在哪」，
 * 给每个竞品一个颜色只会让主角淹掉，还得多跑一遍色盲校验。
 *
 * 实测分离度 ΔE 28.6（正常视觉）/ 23.9（最差色觉类型），两项都 PASS。
 * ⚠️ 竞品填充不许换成 `#64748b` —— 它和 accent 在绿色盲下 ΔE 只有 5.3。
 */
export function EmphasisBars({ data, scale = 1 }: { data: BarDatum[]; scale?: number }) {
  return (
    <div className={styles.bars}>
      {data.map((d) => {
        const r = rate(d.m, d.n)
        const zero = r === 0
        const width = r === null ? 0 : Math.min(100, (r / scale) * 100)

        return (
          <Bar key={d.key} datum={d} r={r} zero={zero} width={width} />
        )
      })}
    </div>
  )
}

function Bar({
  datum,
  r,
  zero,
  width,
}: {
  datum: BarDatum
  r: number | null
  zero: boolean
  width: number
}) {
  return (
    <>
      <div className={`${styles.barLabel} ${datum.own ? styles.barLabelOwn : ''}`} title={datum.label}>
        {datum.label}
      </div>

      <div className={styles.barTrack}>
        {zero ? (
          <div className={`${styles.barFill} ${styles.barZero}`} />
        ) : (
          <div
            className={`${styles.barFill} ${datum.own ? styles.barFillOwn : ''}`}
            style={{ width: `${width}%` }}
          />
        )}
      </div>

      <div
        className={`${styles.barValue} ${datum.own ? styles.barValueOwn : ''} ${
          zero ? styles.barValueZero : ''
        }`}
      >
        {formatRate(r)}　{formatFraction(datum.m, datum.n)}
      </div>
    </>
  )
}
