'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'

import { ErrorState, ui } from '@/components/ui'
import { ApiError } from '@/lib/api/client'
import { getLatestRun } from '@/lib/api/tasks'
import { useAuth } from '@/lib/auth-context'
import { homeRoute, needsLatestRun, TASKS_ROUTE } from '@/lib/l3/home'

/**
 * `/` 按角色分流（A8）。
 *
 * - **超管 / 运营 → `/tasks`。** 他们管多个客户品牌，任务列表就是工作台。
 * - **客户 → 自己那条最新运行所在的任务。** 客户通常只有一个任务，
 *   让他先看一个单行列表再点进去是多余的一层。
 *
 * **落到 `/tasks/{task_id}` 而不是 `/tasks/{task_id}/runs/{run_id}`。**
 * 两者此刻显示的是同一次运行（任务详情自动落到最新），但含义不同：
 * 钉死 run 的那个 URL 明天就不是最新的了，而首页的语义是「给我看最新的」。
 * 带 runId 的链接留给「运营要把某一次发给客户」那个场景。
 */
export function HomeRedirect() {
  const { status, me } = useAuth()
  const router = useRouter()
  const [error, setError] = useState<ApiError | Error | null>(null)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    if (status !== 'authed') return

    // 判定在 `lib/l3/home`（有测试），这里只负责跳。
    // 尤其别改成 `!canWrite(me)` —— 那会把 machine 身份错分成客户。
    if (!needsLatestRun(me?.role)) {
      router.replace(homeRoute(me?.role, null))
      return
    }

    let alive = true
    setError(null)
    getLatestRun()
      .then((run) => {
        if (alive) router.replace(homeRoute(me?.role, run.task_id))
      })
      .catch((e: unknown) => {
        if (!alive) return
        // 一次都没跑过 → 404。这不是错误，是新客户的正常状态。
        // 退回任务列表：那里会显示「还没有任务 / 从未运行」，
        // 比在首页再写一套同义文案好 —— 两份文案迟早会漂。
        if (e instanceof ApiError && e.status === 404) {
          router.replace(homeRoute(me?.role, null))
          return
        }
        setError(e instanceof Error ? e : new Error(String(e)))
      })
    return () => {
      alive = false
    }
  }, [status, me?.role, router, attempt])

  if (error) {
    return (
      <div style={{ display: 'grid', gap: 12, padding: 24 }}>
        <ErrorState
          status={error instanceof ApiError ? error.status : 0}
          message={error instanceof ApiError ? error.detail : '加载失败'}
          onRetry={() => setAttempt((a) => a + 1)}
        />
        {/* 分流失败不该变成死路 —— 任务列表始终可达，客户在那儿一样能点进去 */}
        <Link href={TASKS_ROUTE} className={ui.rowLink}>
          直接去任务列表 →
        </Link>
      </div>
    )
  }

  return <div style={{ color: 'var(--text-tertiary)', padding: 24 }}>正在进入…</div>
}
