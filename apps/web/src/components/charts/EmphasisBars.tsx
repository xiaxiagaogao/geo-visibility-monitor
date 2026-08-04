import { formatFraction, formatRate, rate } from '@/lib/l3/rates'

import styles from './charts.module.css'

export interface BarDatum {
  key: string | number
  label: string
  m: number
  n: number
  own?: boolean
}

/**
 * emphasis 横条 —— 本品用主色，其余统一灰（docs/27 §5.2 规则 2）。
 *
 * 八个品牌不需要八种颜色：读者只关心「我在哪」，
 * 给每个竞品一个颜色只会让主角淹掉，还得跑一遍色盲校验。
 *
 * 每条右侧同时给出百分比与 m/n —— docs/27 §5.3。
 */
export function EmphasisBars({ data, maxRate }: { data: BarDatum[]; maxRate?: number }) {
  // 条长按比率而非绝对值，且共用同一个刻度上限，否则不同行之间没法比
  const scale = maxRate ?? Math.max(...data.map((d) => (d.n > 0 ? d.m / d.n : 0)), 0.0001)

  return (
    <div className={styles.bars}>
      {data.map((d) => {
        const r = rate(d.m, d.n)
        const zero = r === 0
        const width = r === null ? 0 : Math.min(100, (r / scale) * 100)

        return (
          <Row key={d.key} datum={d} r={r} zero={zero} width={width} />
        )
      })}
    </div>
  )
}

function Row({
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
      <div className={`${styles.barLabel} ${datum.own ? styles.barLabelOwn : ''}`}>
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
        {formatRate(r)}
        {'  '}
        {formatFraction(datum.m, datum.n)}
        {zero ? '　未被提及' : ''}
      </div>
    </>
  )
}
