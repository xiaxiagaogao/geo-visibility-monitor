import { rate } from '@/lib/l3/rates'

import styles from './record.module.css'

/**
 * 刻度尺 —— 这套设计的签名元素。
 *
 * 轨道**宽度固定**，按分母切成 n 格，命中的 m 格上墨。于是一个图元同时说了两件事：
 *
 *   · 上墨部分占轨道的比例 = 比率（可以横着扫读，和进度条一样快）
 *   · 格数与格宽 = **分母**（3 次采样是三个大格，18 次是十八个窄格 ——
 *     一眼看出这两个 66.7% 的可信程度不一样）
 *
 * 上一版这里是一条无刻度的实心条：66.7%(12/18) 和 8.3%(1/12) 的轨道一样长，
 * 「比率永远跟着 m/n」只能靠底下那行小字兑现。刻度让它成为图形本身。
 *
 * 三种不能混淆的状态，各有各的画法：
 *
 *   n = 0   **不可算** —— 一格都不画。画一条空轨道等于宣称「0%」，
 *                        而真相是这个数算不出来。
 *   m = 0   **真的是 0** —— n 个格子全空，但第一格描红。
 *                        全空且无标记的话，它和「还在加载」长得一模一样。
 *   n 很大   格宽会掉到亚像素 —— 退化成实心条 + 每 10 格一道刻线。
 *            这个退化本身也是诚实的：分母大到数不清的时候，就别假装能数。
 */

/** 超过这个格数就不再逐格画 —— 再密下去每格不到 2px，是在骗人 */
const MAX_DISCRETE = 40

export function TickScale({
  m,
  n,
  size = 'md',
  tone = 'own',
}: {
  m: number
  n: number
  size?: 'sm' | 'md' | 'lg'
  /** own = 本品（蓝铅笔）· other = 竞品（灰）· 两者对比度已跑过 CVD 验证 */
  tone?: 'own' | 'other'
}) {
  const r = rate(m, n)

  // 分母为 0：不可算。不画轨道，只留一道底线说明「这里本该有东西」。
  if (r === null) {
    return (
      <div className={`${styles.scale} ${styles[size]}`} data-void="true" aria-hidden="true">
        <div className={styles.voidRule} />
      </div>
    )
  }

  const zero = m === 0
  const dense = n > MAX_DISCRETE

  if (dense) {
    // 退化态：实心条 + 每 10 个样本一道刻线
    const decades = Math.floor(n / 10)
    return (
      <div
        className={`${styles.scale} ${styles[size]} ${styles.dense}`}
        data-tone={tone}
        data-zero={zero || undefined}
        aria-hidden="true"
      >
        <div className={styles.denseBed}>
          <div className={styles.denseFill} style={{ width: `${r * 100}%` }} />
          {Array.from({ length: decades }, (_, i) => (
            <span
              key={i}
              className={styles.decade}
              style={{ left: `${(((i + 1) * 10) / n) * 100}%` }}
            />
          ))}
        </div>
      </div>
    )
  }

  return (
    <div
      className={`${styles.scale} ${styles[size]}`}
      data-tone={tone}
      data-zero={zero || undefined}
      aria-hidden="true"
    >
      {Array.from({ length: n }, (_, i) => (
        <span key={i} className={styles.tick} data-on={i < m || undefined} />
      ))}
    </div>
  )
}
