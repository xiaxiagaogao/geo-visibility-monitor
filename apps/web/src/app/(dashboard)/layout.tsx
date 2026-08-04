import type { ReactNode } from 'react'

import { Sidebar } from '@/components/shell/Sidebar'
import shell from '@/components/shell/shell.module.css'
import { Topbar } from '@/components/shell/Topbar'

export default function DashboardLayout({ children }: { children: ReactNode }) {
  return (
    <div className={shell.root}>
      <Topbar />
      <div className={shell.body}>
        <Sidebar />
        <main className={shell.main}>
          <div className={shell.content}>{children}</div>
        </main>
      </div>
    </div>
  )
}
