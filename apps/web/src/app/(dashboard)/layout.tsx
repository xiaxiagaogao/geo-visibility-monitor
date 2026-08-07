import type { ReactNode } from 'react'

import { FilterBar } from '@/components/shell/FilterBar'
import shell from '@/components/shell/shell.module.css'
import { Sidebar } from '@/components/shell/Sidebar'
import { Topbar } from '@/components/shell/Topbar'

export default function DashboardLayout({ children }: { children: ReactNode }) {
  return (
    <div className={shell.root}>
      <Sidebar />
      <div className={shell.body}>
        <Topbar />
        <FilterBar />
        <main className={shell.main}>
          <div className={shell.content}>{children}</div>
        </main>
      </div>
    </div>
  )
}
