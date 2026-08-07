'use client'

import { usePathname } from 'next/navigation'

import { Badge } from '@/components/ui'
import { LAST_COLLECTED_AT } from '@/lib/fixtures'

import styles from './shell.module.css'
import { ThemeToggle } from './ThemeToggle'

/**
 * 页面标题从路由推，不用 context —— 只有 5 条固定路由，
 * 为这点信息拉一层 provider 不划算。
 */
const TITLES: Record<string, { title: string; sub: string }> = {
  '/': { title: '总览', sub: '全局表现速览 · 安踏（运动鞋服）' },
  '/batches/': { title: '采集批次', sub: '按采集日期分组 · 逐批下钻到证据' },
  '/gaps/': { title: '覆盖缺口', sub: '本品缺席或明显落后、竞品在场的提问 · 按失分量排序' },
  '/citations/': { title: '引用分析', sub: 'citations 聚合 · 来源与覆盖分布' },
  '/responses/': { title: '原始回答', sub: '单条 AI 回答溯源 · 正文 / 截图 / 引用' },
}

export function Topbar() {
  const pathname = usePathname()
  const meta = TITLES[pathname] ?? TITLES[`${pathname}/`] ?? { title: 'GEO 监测台', sub: '' }

  return (
    <header className={styles.topbar}>
      <div>
        <div className={styles.filterGroup}>
          <strong style={{ fontSize: 'var(--fs-h1)' }}>{meta.title}</strong>
          {/* 只读定位：配置与发起继续走 /qa，这个前端不做写操作 */}
          <Badge tone="accent">只读</Badge>
        </div>
        <div style={{ fontSize: 'var(--fs-xs)', color: 'var(--text-tertiary)', marginTop: 2 }}>
          {meta.sub}
        </div>
      </div>

      <span className={styles.spacer} />

      <span className={styles.topbarStatus}>
        <span className={styles.statusDot} />
        采集正常 · 更新于 {LAST_COLLECTED_AT}
      </span>

      <button className={styles.iconBtn} aria-label="刷新" title="刷新">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 12a9 9 0 1 1-2.6-6.4" />
          <path d="M21 4v5h-5" />
        </svg>
      </button>

      <ThemeToggle />
    </header>
  )
}
