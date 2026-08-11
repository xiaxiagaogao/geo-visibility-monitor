import type { Metadata } from 'next'
import type { ReactNode } from 'react'

import { ThemeScript } from '@/components/shell/ThemeToggle'
import { AuthProvider } from '@/lib/auth-context'
import '@/styles/globals.css'

export const metadata: Metadata = {
  title: 'GEO 监测台',
  description: '品牌在 AI 回答中的可见度监测 —— 每个数字都能下钻到原文',
}

/**
 * 根布局：html/body、全局样式、主题脚本，以及**全站唯一的 AuthProvider**。
 *
 * Provider 放这里而不是各路由组里：放下面的话登录页和 dashboard 各有一个，
 * 状态不共享 —— 登录成功跳转后会再拉一次 /me，且两边对「我是谁」的认知
 * 可能短暂不一致。
 *
 * Sidebar + Topbar 那层壳仍在 (dashboard) 路由组里 —— 登录页不该套壳。
 */
export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="zh-CN" data-theme="light" suppressHydrationWarning>
      <head>
        <ThemeScript />
      </head>
      <body>
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  )
}
