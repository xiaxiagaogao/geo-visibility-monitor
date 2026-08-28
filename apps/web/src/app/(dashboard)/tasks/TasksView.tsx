'use client'

import Link from 'next/link'
import { useCallback, useEffect, useState } from 'react'

import {
  Blank,
  Fault,
  Mark,
  markTone,
  Pending,
  PageHead,
  Plate,
  kit,
  Table,
} from '@/components/kit'
import { brandNameMap, listBrands } from '@/lib/api/brands'
import { ApiError } from '@/lib/api/client'
import { listTasks } from '@/lib/api/tasks'
import { canWrite } from '@/lib/api/auth'
import { useAuth } from '@/lib/auth-context'
import { runStatusLabel, runStatusTone } from '@/lib/l3/run-status'
import type { Task } from '@/lib/types'

import page from './tasks.module.css'

/**
 * 任务列表 —— 超管/运营的首页。
 *
 * 两个请求：`/v1/tasks` 拿列表，`/v1/brands` 拿品牌名。
 * 列表响应里只有 `brand_id`，名称必须靠 id 关联 —— 和「competitors 按
 * brand_id 关联、不许按数组下标」是同一条纪律。
 *
 * `latest_run_*` 已经在 TaskOut 里，所以**不必逐行再打一次 runs 接口**。
 *
 * 标题写在页面里而不是顶栏：上一版顶栏有一张静态的路由→标题表，
 * 于是这一页「检测任务」连着出现两遍。
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

  return (
    <div className={page.stack}>
      <PageHead
        title="检测任务"
        lede={
          <>
            每个任务盯一个品牌；一次执行叫一个 run，
            <strong>提问集与竞品集在发起那一刻冻结</strong> ——
            所以两次运行之间的差异是表现变化，不是口径变化。
          </>
        }
        action={
          /* 客户是纯只读，按角色隐藏按钮**只是体验，不是安全边界** ——
             服务端的 require_write 才是。 */
          canWrite(me) ? (
            <Link href="/tasks/new" className={kit.link}>
              新建任务 +
            </Link>
          ) : null
        }
      />

      {error ? (
        <Fault
          status={error instanceof ApiError ? error.status : 0}
          message={error instanceof ApiError ? error.detail : '加载失败'}
          onRetry={load}
        />
      ) : (
        <Plate flush>
          <div style={{ padding: 'var(--sp-5) var(--sp-6)' }}>
            {tasks === null ? (
              <div style={{ display: 'grid', gap: 8 }}>
                <Pending height={22} />
                <Pending height={22} />
              </div>
            ) : tasks.length === 0 ? (
              <Blank lead="还没有任务">
                {canWrite(me)
                  ? '建一个任务，选好品牌与平台，就可以发起第一次检测。'
                  : '还没有为你的品牌建立监测任务，请联系运营。'}
              </Blank>
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
                        <Link href={`/tasks/${t.id}`} className={page.taskName}>
                          {t.name}
                        </Link>
                        {t.is_active ? null : (
                          <span style={{ marginLeft: 8 }}>
                            <Mark>已停用</Mark>
                          </span>
                        )}
                      </td>
                      <td>
                        {/* 品牌被删过、或客户看不到那个品牌时，name 会取不到。
                            显示 #id 而不是空白 —— 空白看起来像渲染坏了。 */}
                        {brands.get(t.brand_id) ?? `#${t.brand_id}`}
                      </td>
                      <td className={page.cellMeta}>{t.platforms.join(' · ') || '—'}</td>
                      <td className="mono">{t.samples}</td>
                      <td>
                        <Mark tone={markTone(runStatusTone(t.latest_run_status))} dot>
                          {runStatusLabel(t.latest_run_status)}
                        </Mark>
                        {t.latest_run_at ? (
                          <span className={`${page.cellMeta} mono`} style={{ marginLeft: 8 }}>
                            {t.latest_run_at.slice(0, 10)}
                          </span>
                        ) : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            )}
          </div>
        </Plate>
      )}
    </div>
  )
}
