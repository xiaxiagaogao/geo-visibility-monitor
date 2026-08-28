'use client'

import { useState } from 'react'

import { Mark } from '@/components/kit'
import { canWrite } from '@/lib/api/auth'
import { useAuth } from '@/lib/auth-context'

import styles from './shell.module.css'
import { ThemeToggle } from './ThemeToggle'

/**
 * 顶栏是一条工具轨，**不承载页面标题**。
 *
 * 上一版这里有一张静态的「路由 → 标题」表。它到二级路由为止还成立，
 * 一进 /tasks/[id] 就退化成显示应用名 —— 于是页头同时出现两个标题：
 * 顶栏那个是错的（「GEO 监测台」），页面里那个才是对的（任务名）。
 * 而 /tasks 上两个都对，于是「检测任务」连着出现两遍。
 *
 * 标题归页面自己：只有页面知道这个任务叫什么、这条样本是第几号。
 */
export function Topbar() {
  const { me, logout } = useAuth()
  const [loggingOut, setLoggingOut] = useState(false)
  const [logoutError, setLogoutError] = useState(false)

  async function onLogout() {
    setLoggingOut(true)
    setLogoutError(false)
    try {
      // 成功后 AuthProvider 把 status 置为 anonymous，
      // DashboardShell 的 useRequireAuth 会送去登录页 —— 这里不必自己跳。
      await logout()
    } catch {
      // **失败时绝不本地清状态。** 服务端会话没撤销就显示「已退出」，
      // 是这个界面能撒的最危险的谎：用户以为在公共机器上安全登出了，
      // 而那张会话 Cookie 还活着。
      setLogoutError(true)
      setLoggingOut(false)
    }
  }

  return (
    <header className={styles.topbar}>
      <span className={styles.spacer} />

      {/* 曾经无条件挂「只读」，当时属实 —— 前端一个写操作都没有。
          A5 的「新建任务」和 A6 的「立即运行」上线后它就成了假话，
          所以改成按角色渲染：客户确实是纯只读，超管/运营不是。

          **这只是标注，不是权限。** 真正的边界在服务端的 require_write。 */}
      {me && !canWrite(me) ? <Mark tone="void">只读</Mark> : null}

      {me?.email ? (
        <div className={styles.userBox}>
          <span className={styles.userEmail} title={me.email}>
            {me.email}
          </span>
          <button
            className={styles.linkBtn}
            onClick={onLogout}
            disabled={loggingOut}
            title={logoutError ? '退出失败，请重试' : undefined}
          >
            {logoutError ? '退出失败，重试' : loggingOut ? '退出中…' : '退出账户'}
          </button>
        </div>
      ) : null}

      {/* 整页重载，不是 router.refresh()：这个应用的数据全在客户端 useEffect 里取，
          refresh 只会重跑服务端组件，页面上的数字一个都不会变 —— 那样这颗按钮
          就还是假的，只是从「什么都不做」变成「看起来做了什么」。 */}
      <button
        className={styles.iconBtn}
        aria-label="重新载入整页"
        title="重新载入整页"
        onClick={() => window.location.reload()}
      >
        <svg
          width="15"
          height="15"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.9"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M21 12a9 9 0 1 1-2.6-6.4" />
          <path d="M21 4v5h-5" />
        </svg>
      </button>

      <ThemeToggle />
    </header>
  )
}
