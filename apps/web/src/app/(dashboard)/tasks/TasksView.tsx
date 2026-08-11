'use client'

import Link from 'next/link'
import { useCallback, useEffect, useState } from 'react'

import { Badge, Button, EmptyState, ErrorState, Panel, Skeleton, Table, ui } from '@/components/ui'
import { brandNameMap, listBrands } from '@/lib/api/brands'
import { ApiError } from '@/lib/api/client'
import { listTasks } from '@/lib/api/tasks'
import { canWrite } from '@/lib/api/auth'
import { useAuth } from '@/lib/auth-context'
import { runStatusLabel, runStatusTone } from '@/lib/l3/run-status'
import type { Task } from '@/lib/types'

/**
 * 任务列表 —— 超管/运营的首页。
 *
 * 两个请求：`/v1/tasks` 拿列表，`/v1/brands` 拿品牌名。
 * 列表响应里只有 `brand_id`，名称必须靠 id 关联 —— 和「competitors 按
 * brand_id 关联、不许按数组下标」是同一条纪律。
 *
 * `latest_run_*` 已经在 TaskOut 里，所以**不必逐行再打一次 runs 接口**。
 */
export function TasksView() {
  const { me } = useAuth()
  const [tasks, setTasks] = useState<Task[] | null>(null)
  const [brands, setBrands] = useState<Map<number, string>>(new Map())
  const [error, setError] = useState<ApiError | Error | null>(null)

  const load = useCallback(() => {
    setError(null)
    setTasks(null)
    Promise.all([listTasks(), listBrands()])
      .then(([t, b]) => {
        setTasks(t.items)
        setBrands(brandNameMap(b.items))
      })
      .catch((e: unknown) => setError(e instanceof Error ? e : new Error(String(e))))
  }, [])

  useEffect(load, [load])

  if (error) {
    const status = error instanceof ApiError ? error.status : 0
    return (
      <ErrorState
        status={status}
        message={error instanceof ApiError ? error.detail : '加载失败'}
        onRetry={load}
      />
    )
  }

  return (
    <Panel
      title="检测任务"
      subtitle="每个任务盯一个品牌；一次执行叫一个 run，口径在发起那一刻冻结"
      right={
        // 客户是纯只读，按角色隐藏按钮**只是体验，不是安全边界** ——
        // 服务端的 require_write 才是。
        canWrite(me) ? (
          <Link href="/tasks/new" className={ui.rowLink}>
            新建任务 +
          </Link>
        ) : null
      }
    >
      {tasks === null ? (
        <div style={{ display: 'grid', gap: 8 }}>
          <Skeleton height={20} />
          <Skeleton height={20} />
        </div>
      ) : tasks.length === 0 ? (
        <EmptyState>
          <strong style={{ color: 'var(--text-secondary)' }}>还没有任务</strong>
          <span>
            {canWrite(me)
              ? '建一个任务，选好品牌与平台，就可以发起第一次检测。'
              : '还没有为你的品牌建立监测任务，请联系运营。'}
          </span>
        </EmptyState>
      ) : (
        <Table>
          <thead>
            <tr>
              <th>任务</th>
              <th>品牌</th>
              <th>平台</th>
              <th>采样</th>
              <th>最近运行</th>
            </tr>
          </thead>
          <tbody>
            {tasks.map((t) => (
              <tr key={t.id}>
                <td>
                  <Link href={`/tasks/${t.id}`} className={ui.rowLink}>
                    {t.name}
                  </Link>
                  {t.is_active ? null : (
                    <span style={{ marginLeft: 6 }}>
                      <Badge tone="neutral">已停用</Badge>
                    </span>
                  )}
                </td>
                <td>
                  {/* 品牌被删过、或客户看不到那个品牌时，name 会取不到。
                      显示 #id 而不是空白 —— 空白看起来像渲染坏了。 */}
                  {brands.get(t.brand_id) ?? `#${t.brand_id}`}
                </td>
                <td style={{ color: 'var(--text-secondary)', fontSize: 'var(--fs-xs)' }}>
                  {t.platforms.join(' · ') || '—'}
                </td>
                <td className={ui.numeric}>{t.samples}</td>
                <td>
                  <Badge tone={runStatusTone(t.latest_run_status)}>
                    {runStatusLabel(t.latest_run_status)}
                  </Badge>
                  {t.latest_run_at ? (
                    <span
                      className={ui.numeric}
                      style={{ marginLeft: 8, color: 'var(--text-tertiary)', fontSize: 'var(--fs-xs)' }}
                    >
                      {t.latest_run_at.slice(0, 10)}
                    </span>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
    </Panel>
  )
}
