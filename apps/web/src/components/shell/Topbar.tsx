'use client'

import { usePathname } from 'next/navigation'

import { Badge } from '@/components/ui'
import { canWrite } from '@/lib/api/auth'
import { useAuth } from '@/lib/auth-context'

import styles from './shell.module.css'
import { ThemeToggle } from './ThemeToggle'

/**
 * 页面标题从路由推，不用 context。
 *
 * ⚠️ **静态表只够用到二级路由。** 到了 /tasks/[id] 这种带 id 的页面，
 * 标题得是任务名、副标题得是品牌 —— 那些只有数据到手才知道，
 * 届时要么让页面自己往上报，要么改成 context。别再往这张表里堆。
 */
const TITLES: Record<string, { title: string; sub: string }> = {
  // `/` 自己不渲染内容，只按角色分流（A8）。写「总览」会闪一下一个
  // 并不存在的页面名 —— 那个单品牌总览看板早随旧 IA 删了。
  '/': { title: 'GEO 监测台', sub: '正在按角色进入…' },
  '/tasks': { title: '检测任务', sub: '每个任务盯一个品牌 · 一次执行叫一个 run' },
  '/tasks/new': { title: '新建任务', sub: '' },
}

export function Topbar() {
  const pathname = usePathname()
  const { me } = useAuth()
  const meta = TITLES[pathname] ?? TITLES[`${pathname}/`] ?? { title: 'GEO 监测台', sub: '' }

  return (
    <header className={styles.topbar}>
      <div>
        <div className={styles.filterGroup}>
          <strong style={{ fontSize: 'var(--fs-h1)' }}>{meta.title}</strong>
          {/* 曾经无条件挂「只读」，当时属实 —— 前端一个写操作都没有。
              A5 的「新建任务」和 A6 的「立即运行」上线后它就成了假话，
              所以改成按角色渲染：客户确实是纯只读，超管/运营不是。

              **这只是标注，不是权限。** 真正的边界在服务端的 require_write。 */}
          {canWrite(me) ? null : <Badge tone="accent">只读</Badge>}
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
