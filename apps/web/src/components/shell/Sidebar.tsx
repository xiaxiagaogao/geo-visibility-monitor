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
 * 「用户管理」只对超管显示 —— 它是**唯一**一个连读都要超管的入口
 * （`/v1/users/*` 挂 require_superadmin），运营看到了也点不动。
 */
const NAV = [
  { href: '/tasks', label: '检测任务', icon: SheetIcon },
  { href: '/brands', label: '品牌', icon: GridIcon },
]

const ADMIN_NAV = [{ href: '/users', label: '用户管理', icon: PeopleIcon }]

export function Sidebar() {
  const pathname = usePathname()
  const { me } = useAuth()

  return (
    <aside className={styles.sidebar}>
      <div className={styles.brand}>
        <TraceMark />
        <div className={styles.brandText}>
          <span className={styles.brandName}>GEO 监测台</span>
          <span className={styles.brandSub}>AI 回答可见度监测</span>
        </div>
      </div>

      <nav className={styles.nav}>
        {[...NAV, ...(isSuperadmin(me) ? ADMIN_NAV : [])].map(({ href, label, icon: Ico }) => {
          const active = href === '/' ? pathname === '/' : pathname.startsWith(href)
          return (
            <Link
              key={href}
              href={href}
              className={`${styles.navItem} ${active ? styles.navItemOn : ''}`}
              aria-current={active ? 'page' : undefined}
            >
              <Ico />
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
            {/* 用 `navAside` 不用 `navItem`：它和「检测任务 / 品牌」不是同一类东西。
                产品导航是客户买的那套；这是运维后门。视觉重量一样的话，
                等于宣称它们同级。 */}
            <a className={styles.navAside} href="/qa" target="_blank" rel="noreferrer">
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
      <div className={styles.sideFoot}>分母口径 answer_status = ok</div>
    </aside>
  )
}

/**
 * 字标 —— 一段可见度读数：走平、一个尖峰、再走平。
 *
 * 上一版是个放大镜，那是「搜索」的通用符号，和这个产品没关系。
 * 这一枚说的是这个产品实际在做的事：持续记录，偶尔出现一次事件。
 */
function TraceMark() {
  return (
    <svg
      className={styles.brandMark}
      viewBox="0 0 30 30"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <rect x="1.4" y="1.4" width="27.2" height="27.2" rx="2.5" strokeWidth="1.3" opacity="0.4" />
      {/* 刻度 */}
      <path d="M7 5.6v2M12 5.6v2M17 5.6v2M22 5.6v2" strokeWidth="1.1" opacity="0.45" />
      {/* 走过的轨迹 */}
      <path d="M4 17h4.4l1.9-3.2 2 8.6 2.3-11.9 2.2 6.8 1.7-2.8H26" />
    </svg>
  )
}

/* ── 图标：16px 线性，一致的 1.9 描边，跟随 currentColor ── */

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

/** 底格：带刻度的读数区 */
function SheetIcon() {
  return (
    <Icon>
      <rect x="3" y="3.5" width="18" height="17" rx="2" />
      <path d="M3 8.5h18" />
      <path d="M7 3.5v3M12 3.5v3M17 3.5v3" strokeWidth="1.4" />
      <path d="M6.5 14.5h3l1.4-3 1.6 5 1.5-4h3" />
    </Icon>
  )
}

/** 榜：三道长短不一的横条 */

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

function PeopleIcon() {
  return (
    <Icon>
      <circle cx="9" cy="8" r="3.4" />
      <path d="M2.8 20a6.2 6.2 0 0 1 12.4 0" />
      <path d="M16.2 5.2a3.4 3.4 0 0 1 0 6.6M17.6 14.6A6.2 6.2 0 0 1 21.4 20" />
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
