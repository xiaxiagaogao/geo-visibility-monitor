import type { Metadata } from 'next'
import type { ReactNode } from 'react'

import '@/styles/globals.css'

export const metadata: Metadata = {
  title: 'GEO 监测台',
  description: '品牌在 AI 回答中的可见度监测 —— 每个数字都能下钻到原文',
}

/**
 * 根布局只管 html/body 和全局样式。
 * Topbar + Sidebar 那层壳在 (dashboard) 路由组里 —— 登录页不该套壳。
 */
export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  )
}
