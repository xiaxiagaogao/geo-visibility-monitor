'use client'

import { useState, type ReactNode } from 'react'

import styles from './kit.module.css'

/**
 * 折叠提示条 —— 把若干条口径警示压成**一行**，点开才展全文。
 *
 * ## 为什么需要它
 *
 * 任务详情页首屏一度被四段说明文字占掉：断口警告、断点判据的限度、
 * 部分成功、这次运行的口径说明。实测合计 **307px**，
 * 而视口高 759px —— **四个读数全部落在折叠线以下，首屏一个数字都看不到**。
 * 这正面违反风格情报 §8.2「首屏只回答四个问题」。
 *
 * ## 但一条都不能删
 *
 * 那四段全是这个产品拒绝说好听话的地方 —— 删掉等于把「诚实」优化掉。
 * 所以不是删，是**换呈现**：默认一行摘要，想读随时展开。
 *
 * 摘要行**必须带上最重的那一条的语气**（有 fault 就红、有 alert 就琥珀），
 * 否则折叠等于把警告藏起来。
 */

export interface Notice {
  /** 摘要行里显示的短标签，例如「4 处口径断点」 */
  label: string
  /** 展开后的全文 */
  body: ReactNode
  tone?: 'plain' | 'alert' | 'fault'
}

export function Notices({ items, defaultOpen = false }: { items: Notice[]; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen)
  if (items.length === 0) return null

  // 最重的语气代表整条 —— 折叠不能把警告的分量一起折掉
  const worst: 'plain' | 'alert' | 'fault' = items.some((n) => n.tone === 'fault')
    ? 'fault'
    : items.some((n) => n.tone === 'alert')
      ? 'alert'
      : 'plain'

  return (
    <div className={`${styles.notices} ${worst === 'fault' ? styles.noticesFault : ''} ${
      worst === 'alert' ? styles.noticesAlert : ''
    }`}>
      <button
        type="button"
        className={styles.noticesBar}
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span className={styles.noticesLabels}>
          {items.map((n, i) => (
            <span key={i} className={styles.noticesLabel}>
              {n.label}
            </span>
          ))}
        </span>
        <span className={styles.noticesToggle}>
          {open ? '收起' : `展开 ${items.length} 条`}
        </span>
      </button>

      {open ? (
        <div className={styles.noticesBody}>
          {items.map((n, i) => (
            <p key={i} className={styles.noticesItem}>
              {n.body}
            </p>
          ))}
        </div>
      ) : null}
    </div>
  )
}
