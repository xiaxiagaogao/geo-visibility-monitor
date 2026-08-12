'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import type { ReactNode } from 'react'

import { canWrite, isSuperadmin } from '@/lib/api/auth'
import { useAuth } from '@/lib/auth-context'

import styles from './shell.module.css'

/**
 * 导航。**不分组** —— 入口少的时候加分组标题只是噪音。
 *
 * 「引用分析」不会回来：citations 全库 0 行，根因是采集时从未开联网搜索，
 * 不是能补个字段解决的（API.md §9）。
 *
 * 「用户管理」只对超管显示 —— 它是**唯一**一个连读都要超管的入口
 * （`/v1/users/*` 挂 require_superadmin），运营看到了也点不动。
 */
const NAV = [
  { href: '/tasks', label: '检测任务', icon: LayersIcon },
  { href: '/brands', label: '品牌', icon: GridIcon },
]

const ADMIN_NAV = [{ href: '/users', label: '用户管理', icon: MessageIcon }]

export function Sidebar() {
  const pathname = usePathname()
  const { me } = useAuth()

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
        {[...NAV, ...(isSuperadmin(me) ? ADMIN_NAV : [])].map(({ href, label, icon: Icon }) => {
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

        {/* 运维质检对**客户不可见**。/qa 是运维后门，不是产品功能 ——
            给客户露一个「运维」入口，轻则让他以为那是他该用的东西，
            重则让他觉得自己看的这套系统还在调试。

            这和按角色隐藏写操作按钮不是一回事：那种隐藏只是体验，
            真边界在服务端。这里隐藏的是**产品边界** —— 客户买的是监测报告，
            不是我们的运维台。 */}
        {canWrite(me) ? (
          <>
            <div className={styles.navSep} />
            {/* 不重做 B7 QA，链过去就行 */}
            <a className={styles.navItem} href="/qa" target="_blank" rel="noreferrer">
              <ToolIcon />
              运维质检 ↗
            </a>
          </>
        ) : null}
      </nav>

      {/* A2-A4 做完之后，建品牌 / 管提问词 / 管用户 / 发起抓取都在产品前端里了。
          /qa 还留着，是因为它另有产品前端不覆盖的运维动作（重标注、job 重试、
          触发 worker）。要不要彻底下掉是产品决定，不是「顺手清理」—— 所以
          先留着并按角色藏起来，没有替代品之前拿掉它等于让运维没手可用。 */}
      <div className={styles.sideFoot}>数据口径 L2 counts</div>
    </aside>
  )
}

/* ── 图标：16px 线性，stroke 跟随 currentColor ──
   AlertIcon / LinkIcon 暂时没人用，留着给以后的入口，别当死代码删。 */

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
