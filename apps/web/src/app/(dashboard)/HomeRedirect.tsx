'use client'

import { useRouter } from 'next/navigation'
import { useEffect } from 'react'

import { useAuth } from '@/lib/auth-context'

/**
 * `/` 按角色分流。
 *
 * IA 定的终态是：超管/运营 → 任务列表；**客户 → 自己品牌的最新 run**。
 * 客户那一半要等任务详情页（A6）做出来才有地方可去，在那之前两种角色
 * 都落到任务列表 —— 列表接口本身按 workspace 收敛，客户看到的就是自己那份，
 * 不会串。
 */
export function HomeRedirect() {
  const { status } = useAuth()
  const router = useRouter()

  useEffect(() => {
    if (status === 'authed') router.replace('/tasks')
  }, [status, router])

  return (
    <div style={{ color: 'var(--text-tertiary)', padding: 24 }}>正在进入…</div>
  )
}
