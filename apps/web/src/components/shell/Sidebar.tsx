'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import type { ReactNode } from 'react'

import styles from './shell.module.css'

/**
 * 导航 —— **等 IA 定稿**，现在只有占位一条。
 *
 * 原来是五条：总览 / 采集批次 / 覆盖缺口 / 引用分析 / 原始回答。
 * 它们随单品牌页面一起删了，原因不是页面做得不好，是这套 IA 的前提错了：
 * 五条全部隐含「当前只有一个被监测品牌」，没有品牌或检测任务这一层。
 *
 * 重建时至少要先回答：入口是任务列表还是品牌列表？
 * 「引用分析」不必回来（citations 全库 0 行且根因不可修，API.md §9）。
 *
 * 「不分组」这条判断可以留着 —— 入口少的时候加分组标题只是噪音。
 */
const NAV = [{ href: '/', label: '总览', icon: GridIcon }]

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

      {/* 「配置与发起走 /qa」是把这个前端定位成纯看板时写的，和产品方向已经不符：
          /qa 是运维质检页，不是正式产品前端，而超管/运营本来就该在这里
          建品牌、管提问词、发起抓取（API.md §3）。IA 定稿时这行要改。 */}
      <div className={styles.sideFoot}>数据口径 L2 counts</div>
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
