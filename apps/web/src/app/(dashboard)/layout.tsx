import type { ReactNode } from 'react'

import { DashboardShell } from './DashboardShell'

/**
 * 外壳骨架 + 登录闸门。AuthProvider 在根布局，这里不再包一层。
 *
 * 原来这里还有一条 <FilterBar />，已随单品牌页面一起删掉 ——
 * 它把「品牌」渲染成两个写死的 span（安踏本品 vs 7 个竞品），不是控件。
 * 多品牌 / 检测任务的 IA 定下来之后重做，届时品牌大概率不再是
 * 全局筛选条上的一个维度，而是任务本身的属性。
 */
export default function DashboardLayout({ children }: { children: ReactNode }) {
  return <DashboardShell>{children}</DashboardShell>
}
