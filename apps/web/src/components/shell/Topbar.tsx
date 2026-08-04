import { BRANDS, PLATFORMS } from '@/lib/fixtures'

import styles from './shell.module.css'

/**
 * 顶栏 = 「当前在看谁、在哪些平台、什么时间窗」。
 *
 * 平台放顶栏而不是筛选行 —— 它表达的是**能力边界**（只有 DeepSeek 接了），
 * 不是一个普通筛选项。竞品把平台塞进筛选行是因为它四个平台都真跑得动。
 */
export function Topbar() {
  const brand = BRANDS[0]

  return (
    <header className={styles.topbar}>
      <span className={styles.logo}>GEO 监测台</span>
      <span className={styles.divider} />

      <div className={styles.brandSwitch}>
        <span className={styles.brandSwitchLabel}>监测品牌</span>
        <span className={styles.brandSwitchValue}>{brand.name}</span>
        <span className={styles.caret}>▾</span>
      </div>

      <div className={styles.pills}>
        {PLATFORMS.map((p) => (
          <span
            key={p.id}
            className={`${styles.pill} ${p.connected ? styles.pillOn : styles.pillOff}`}
            title={p.connected ? undefined : '该平台尚未接入，无数据'}
          >
            {p.connected ? p.label : `${p.label} · 未接入`}
          </span>
        ))}
      </div>

      <span className={styles.spacer} />

      <span className={styles.provenance}>数据口径：L2 counts · 已排除假数据</span>
      <span className={styles.pill}>全部时间</span>
    </header>
  )
}
