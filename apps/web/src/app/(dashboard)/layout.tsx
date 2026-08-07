import type { ReactNode } from 'react'

import shell from '@/components/shell/shell.module.css'
import { Sidebar } from '@/components/shell/Sidebar'
import { Topbar } from '@/components/shell/Topbar'

/**
 * 外壳骨架。
 *
 * 原来这里还有一条 <FilterBar />，已随单品牌页面一起删掉 ——
 * 它把「品牌」渲染成两个写死的 span（安踏本品 vs 7 个竞品），
 * 不是控件。多品牌 / 检测任务的 IA 定下来之后重做，届时品牌大概率
 * 不再是全局筛选条上的一个维度，而是任务本身的属性。
 */
export default function DashboardLayout({ children }: { children: ReactNode }) {
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
