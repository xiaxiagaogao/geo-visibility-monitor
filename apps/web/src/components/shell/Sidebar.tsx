'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import type { ReactNode } from 'react'

import styles from './shell.module.css'

/**
 * 五个入口，**不分组**。
 *
 * GeoMonitor 用「分析 / 内容 / 设计系统」三组标题，那是因为它是内容生产全链路；
 * 我们砍到一组，加标题只是噪音。
 *
 * 覆盖缺口排第三 —— 它是唯一数据完全齐备且输出可执行的页。
 */
const NAV = [
  { href: '/', label: '总览', icon: GridIcon },
  { href: '/batches/', label: '采集批次', icon: LayersIcon },
  { href: '/gaps/', label: '覆盖缺口', icon: AlertIcon },
  { href: '/citations/', label: '引用分析', icon: LinkIcon },
  { href: '/responses/', label: '原始回答', icon: MessageIcon },
]

export function Sidebar() {
  const pathname = usePathname()

  return (
    <aside className={styles.sidebar}>
      <div className={styles.brand}>
        <div className={styles.mark}>
          <svg
            width="19"
            height="19"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.4"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <circle cx="11" cy="11" r="7" />
            <path d="M21 21l-4.3-4.3" />
          </svg>
        </div>
        <div className={styles.brandText}>
          <span className={styles.brandName}>GEO 监测台</span>
          <span className={styles.brandSub}>AI 回答可见度监测</span>
        </div>
      </div>

      <nav className={styles.nav}>
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = href === '/' ? pathname === '/' : pathname.startsWith(href)
          return (
            <Link
              key={href}
              href={href}
              className={`${styles.navItem} ${active ? styles.navItemOn : ''}`}
              aria-current={active ? 'page' : undefined}
            >
              <Icon />
              {label}
            </Link>
          )
        })}

        <div className={styles.navSep} />

        {/* 不重做 B7 QA，链过去就行 */}
        <a className={styles.navItem} href="/qa" target="_blank" rel="noreferrer">
          <ToolIcon />
          运维质检 ↗
        </a>
      </nav>

      <div className={styles.sideFoot}>
        只读看板 · 数据口径 L2 counts
        <br />
        配置与发起走 /qa
      </div>
    </aside>
  )
}

/* ── 图标：16px 线性，stroke 跟随 currentColor ── */

function Icon({ children }: { children: ReactNode }) {
  return (
    <svg
      className={styles.navIcon}
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.9"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {children}
    </svg>
  )
}

function GridIcon() {
  return (
    <Icon>
      <rect x="3" y="3" width="7" height="7" rx="1.5" />
      <rect x="14" y="3" width="7" height="7" rx="1.5" />
      <rect x="3" y="14" width="7" height="7" rx="1.5" />
      <rect x="14" y="14" width="7" height="7" rx="1.5" />
    </Icon>
  )
}

function LayersIcon() {
  return (
    <Icon>
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <path d="M3 9h18M9 9v11" />
    </Icon>
  )
}

function AlertIcon() {
  return (
    <Icon>
      <path d="M10.3 3.6 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.6a2 2 0 0 0-3.4 0Z" />
      <path d="M12 9v4M12 17h.01" />
    </Icon>
  )
}

function LinkIcon() {
  return (
    <Icon>
      <path d="M4 6h16M4 12h10M4 18h7" />
    </Icon>
  )
}

function MessageIcon() {
  return (
    <Icon>
      <path d="M21 11.5a8.4 8.4 0 0 1-9 8.4 8.4 8.4 0 0 1-3.8-.9L3 21l2-4.6A8.4 8.4 0 0 1 12 3a8.4 8.4 0 0 1 9 8.5Z" />
    </Icon>
  )
}

function ToolIcon() {
  return (
    <Icon>
      <path d="M14.7 6.3a4 4 0 0 0 5 5l-9.4 9.4a2.1 2.1 0 0 1-3-3Z" />
      <path d="M18 2l4 4" />
    </Icon>
  )
}
