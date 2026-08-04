'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'

import styles from './shell.module.css'

const NAV = [
  { href: '/', label: '总览' },
  { href: '/responses/', label: '回答明细' },
  { href: '/jobs/', label: '抓取任务' },
]

/**
 * 三个入口就够（docs/23 §2）。
 * 竞品把侧栏按「第一步…第四步」分组，是因为它是内容生产全链路；
 * 我们只做监测，分组反而是虚张声势。
 */
export function Sidebar() {
  const pathname = usePathname()

  return (
    <nav className={styles.sidebar}>
      {NAV.map((item) => {
        const active = item.href === '/' ? pathname === '/' : pathname.startsWith(item.href)
        return (
          <Link
            key={item.href}
            href={item.href}
            className={`${styles.navLink} ${active ? styles.navLinkOn : ''}`}
          >
            {item.label}
          </Link>
        )
      })}

      <div className={styles.navSep} />

      {/* 不重做 B7 QA，链过去就行（docs/21 §8.5） */}
      <a className={styles.navLink} href="/qa" target="_blank" rel="noreferrer">
        运维质检 ↗
      </a>
    </nav>
  )
}
