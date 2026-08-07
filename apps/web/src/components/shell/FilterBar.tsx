'use client'

import { BRAND_NAMES, OWN_BRAND_ID, PLATFORMS, TOTALS } from '@/lib/fixtures'

import styles from './shell.module.css'

const RANGES = [
  { id: 'all', label: '全部' },
  { id: 'latest', label: '最近一批' },
]

/**
 * 全局筛选条 —— **压成一行**。
 *
 * GeoMonitor 把「更多筛选」单独放第二行，那行只有一个按钮，白占 44px 高度。
 *
 * 选中值最终要 ⇄ URL query 双向同步（URL 是唯一状态源，刷新/分享/后退才自洽），接 API 时接上；
 * 现在固定数据只有一个品牌一个平台，先把控件形态定下来。
 */
export function FilterBar() {
  const competitors = TOTALS.competitors.map((c) => BRAND_NAMES[c.brandId]).join(' · ')

  return (
    <div className={styles.filterBar}>
      <div className={styles.filterGroup}>
        <span className={styles.filterLabel}>平台</span>
        {PLATFORMS.map((p) => (
          <span
            key={p.id}
            className={`${styles.chip} ${p.connected ? styles.chipOn : styles.chipOff}`}
            title={p.connected ? undefined : '该平台尚未接入，没有任何数据'}
            aria-disabled={!p.connected}
          >
            <span
              className={styles.chipDot}
              style={{ background: p.connected ? 'var(--platform-deepseek)' : 'var(--text-tertiary)' }}
            />
            {p.connected ? p.label : `${p.label} · 未接入`}
          </span>
        ))}
      </div>

      <span className={styles.divider} />

      <div className={styles.filterGroup}>
        <span className={styles.filterLabel}>时间</span>
        <div className={styles.seg}>
          {RANGES.map((r, i) => (
            <button key={r.id} className={`${styles.segItem} ${i === 0 ? styles.segOn : ''}`}>
              {r.label}
            </button>
          ))}
        </div>
      </div>

      <span className={styles.divider} />

      <div className={styles.filterGroup}>
        <span className={styles.filterLabel}>品牌</span>
        <span className={`${styles.chip} ${styles.chipOn}`}>
          {BRAND_NAMES[OWN_BRAND_ID]}（本品）
        </span>
        <span className={styles.filterLabel}>vs</span>
        <span className={styles.chip} title={competitors}>
          {TOTALS.competitors.length} 个竞品
        </span>
      </div>

      <span className={styles.spacer} />

      <button className={styles.chip}>更多筛选</button>
    </div>
  )
}
