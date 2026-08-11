'use client'

import type { ReactNode } from 'react'

import shell from '@/components/shell/shell.module.css'
import { Sidebar } from '@/components/shell/Sidebar'
import { Topbar } from '@/components/shell/Topbar'
import { useRequireAuth } from '@/lib/auth-context'

/**
 * 未登录就送去登录页；`loading` 阶段**不渲染内容**。
 *
 * 不渲染是有意的：在还不知道自己是谁的时候把页面画出来，用户会先看到
 * 一屏空数据再突然跳变，或者看到本该按角色隐藏的东西闪一下。
 */
export function DashboardShell({ children }: { children: ReactNode }) {
  const status = useRequireAuth()

  if (status !== 'authed') {
    return (
      <div className={shell.root}>
        <div className={shell.body}>
          <main className={shell.main}>
            <div className={shell.content} style={{ color: 'var(--text-tertiary)', padding: 24 }}>
              {status === 'loading' ? '正在确认身份…' : '未登录，正在跳转…'}
            </div>
          </main>
        </div>
      </div>
    )
  }

  return (
    <div className={shell.root}>
      <Sidebar />
      <div className={shell.body}>
        <Topbar />
        <main className={shell.main}>
          <div className={shell.content}>{children}</div>
        </main>
      </div>
    </div>
  )
}
