'use client'

import { usePathname } from 'next/navigation'

import { Badge } from '@/components/ui'

import styles from './shell.module.css'
import { ThemeToggle } from './ThemeToggle'

/**
 * 页面标题从路由推，不用 context。
 *
 * ⚠️ 这张表原来有 5 条路由，副标题里还写死了「安踏（运动鞋服）」——
 * 那是单品牌看板的产物。路由随页面一起删了，这里只留总览一条占位，
 * 等检测任务 / 多品牌 IA 定下来重建。
 * 届时副标题多半得从当前任务或品牌推出来，不能再是静态字符串。
 */
const TITLES: Record<string, { title: string; sub: string }> = {
  '/': { title: '总览', sub: 'IA 重构中' },
}

export function Topbar() {
  const pathname = usePathname()
  const meta = TITLES[pathname] ?? TITLES[`${pathname}/`] ?? { title: 'GEO 监测台', sub: '' }

  return (
    <header className={styles.topbar}>
      <div>
        <div className={styles.filterGroup}>
          <strong style={{ fontSize: 'var(--fs-h1)' }}>{meta.title}</strong>
          {/* 「只读」现在属实（前端还没有任何写操作），但它不是产品终态：
              三角色里超管/运营要能发起抓取、重试、改配置（API.md §3）。
              IA 定稿时这个徽章要么按角色渲染，要么去掉。 */}
          <Badge tone="accent">只读</Badge>
        </div>
        <div style={{ fontSize: 'var(--fs-xs)', color: 'var(--text-tertiary)', marginTop: 2 }}>
          {meta.sub}
        </div>
      </div>

      <span className={styles.spacer} />

      {/* 原来这里是「采集正常 · 更新于 08-02 10:41」，时间取自固定数据里的常量。
          接 API 后应取最新一条 response 的 created_at；在那之前不放，
          因为一个写死的时间戳会让人以为数据是新的。 */}

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
