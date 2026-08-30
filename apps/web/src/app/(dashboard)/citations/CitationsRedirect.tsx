'use client'

import { useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'

import { Blank, Fault, Pending, Plate } from '@/components/kit'
import { listBrands } from '@/lib/api/brands'
import { ApiError } from '@/lib/api/client'
import { listTasks } from '@/lib/api/tasks'
import { classifyBrands, defaultMonitoredBrandId } from '@/lib/l3/brand-roles'

/**
 * 把旧的 `/citations` 转到某个品牌的引用榜。
 *
 * 落在哪个品牌不能瞎选：`/v1/brands` 里绝大多数是竞品，随手拿第一个会落在
 * 一个永远没有引用的品牌上、满屏空态。判据在 `lib/l3/brand-roles`
 * —— 有任务的优先（引用只可能来自跑过的运行）。
 *
 * **`replace` 而不是 `push`**：这是个转发地址，不该在浏览器历史里留一格，
 * 否则用户按返回会被弹回这里、再次被转走，出不去。
 */
export function CitationsRedirect() {
  const router = useRouter()
  const [error, setError] = useState<Error | null>(null)
  const [empty, setEmpty] = useState(false)

  useEffect(() => {
    let alive = true
    Promise.all([listBrands(), listTasks()])
      .then(([b, t]) => {
        if (!alive) return
        const id = defaultMonitoredBrandId(classifyBrands(b.items, t.items))
        if (id === null) setEmpty(true)
        else router.replace(`/brands/${id}/citations`)
      })
      .catch((e: unknown) => {
        if (alive) setError(e instanceof Error ? e : new Error(String(e)))
      })
    return () => {
      alive = false
    }
  }, [router])

  if (error) {
    return (
      <Fault
        status={error instanceof ApiError ? error.status : 0}
        message={error instanceof ApiError ? error.detail : '加载失败'}
        onRetry={() => router.refresh()}
      />
    )
  }

  if (empty) {
    return (
      <Plate>
        <Blank lead="还没有被监测的品牌">
          引用榜是按被监测品牌看的，入口在品牌详情里。先建一个品牌并给它建任务。
        </Blank>
      </Plate>
    )
  }

  return <Pending height={128} />
}
