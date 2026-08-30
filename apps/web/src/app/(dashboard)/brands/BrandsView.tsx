'use client'

import Link from 'next/link'
import { useCallback, useEffect, useState } from 'react'

import { Blank, Fault, PageHead, Plate, Pending, Table, kit } from '@/components/kit'
import { canWrite } from '@/lib/api/auth'
import { listBrands } from '@/lib/api/brands'
import { ApiError } from '@/lib/api/client'
import { listTasks } from '@/lib/api/tasks'
import { useAuth } from '@/lib/auth-context'
import { classifyBrands, type ClassifiedBrand } from '@/lib/l3/brand-roles'
import type { Brand } from '@/lib/types'

/**
 * 品牌列表（A2）—— **只列监测对象**。
 *
 * 改版前这里平铺全部 17 个品牌，其中 15 个是作为对照存在的竞品。
 * 后果不是难看：竞品列 15/17 是空的，而真正该被看见的那 2 行淹在里面。
 * 现在竞品收进各自监测品牌的详情页（`competitor_ids` 那一栏），
 * 它们的详情页仍然可达 —— 只是不再和监测对象平级排在这张表上。
 *
 * 分类判据在 `lib/l3/brand-roles`（含「刚新建的品牌不能消失」那条），有测试钉着。
 *
 * **`workspace_id` 单独占一列，不是凑数。** 它决定哪些客户账号能看到这个品牌，
 * 而且**建完就改不了**（`BrandUpdate` 里没有这个字段）。把它藏起来的话，
 * 建错 workspace 只能删了重建 —— 而删品牌是级联删除。
 */
export function BrandsView() {
  const { me } = useAuth()
  const [brands, setBrands] = useState<Brand[] | null>(null)
  const [monitored, setMonitored] = useState<ClassifiedBrand[] | null>(null)
  const [referenceCount, setReferenceCount] = useState(0)
  const [error, setError] = useState<Error | null>(null)

  const load = useCallback(() => {
    setError(null)
    setBrands(null)
    setMonitored(null)
    // 要 tasks 才分得出角色 —— 「有任务」是监测对象最硬的证据
    Promise.all([listBrands(), listTasks()])
      .then(([b, t]) => {
        const roster = classifyBrands(b.items, t.items)
        setBrands(b.items)
        setMonitored(roster.monitored)
        setReferenceCount(roster.reference.length)
      })
      .catch((e: unknown) => setError(e instanceof Error ? e : new Error(String(e))))
  }, [])

  useEffect(load, [load])

  if (error) {
    return (
      <Fault
        status={error instanceof ApiError ? error.status : 0}
        message={error instanceof ApiError ? error.detail : '加载失败'}
        onRetry={load}
      />
    )
  }

  return (
    <div className={kit.pageStack}>
      <PageHead
        title="品牌"
        lede="别名决定 L1 能不能认出它；竞品集决定缺口清单和失分量跟谁比。"
        meta={
          referenceCount > 0 ? (
            <span>
              另有 {referenceCount} 个品牌只作为竞品参照存在，在各自对照的品牌里管理
            </span>
          ) : undefined
        }
        action={
          canWrite(me) ? (
            <Link href="/brands/new" className={kit.link}>
              新建品牌 +
            </Link>
          ) : null
        }
      />

      <Plate>
        {monitored === null || brands === null ? (
          <div style={{ display: 'grid', gap: 8 }}>
            <Pending height={20} />
            <Pending height={20} />
          </div>
        ) : monitored.length === 0 ? (
          <Blank lead="还没有被监测的品牌">
            {canWrite(me)
              ? '先建一个品牌，配好别名与竞品，才能给它建监测任务。'
              : '你的 workspace 下还没有品牌，请联系运营。'}
          </Blank>
        ) : (
          <Table>
            <thead>
              <tr>
                <th>品牌</th>
                <th>行业</th>
                <th>workspace</th>
                <th>别名</th>
                <th>竞品</th>
                <th>任务</th>
              </tr>
            </thead>
            <tbody>
              {monitored.map(({ brand: b, taskCount }) => (
                <tr key={b.id}>
                  <td>
                    <Link href={`/brands/${b.id}`} className={kit.rowLink}>
                      {b.name}
                    </Link>
                    {b.name_en ? (
                      <span
                        style={{
                          marginLeft: 6,
                          color: 'var(--text-3)',
                          fontSize: 'var(--fs-label)',
                        }}
                      >
                        {b.name_en}
                      </span>
                    ) : null}
                  </td>
                  <td style={{ color: 'var(--text-2)', fontSize: 'var(--fs-label)' }}>
                    {b.industry || '—'}
                  </td>
                  <td className={kit.numeric}>{b.workspace_id}</td>
                  <td>
                    {/* 别名为 0 时明说，不显示空白 —— 没有别名意味着 L1 只能靠
                        品牌名原样匹配，漏检率会高，这是配置问题不是展示问题 */}
                    {b.aliases.length === 0 ? (
                      <span style={{ color: 'var(--down)', fontSize: 'var(--fs-label)' }}>
                        未配别名
                      </span>
                    ) : (
                      <span
                        style={{ fontSize: 'var(--fs-label)', color: 'var(--text-2)' }}
                        title={b.aliases.join(' · ')}
                      >
                        {b.aliases.slice(0, 3).join(' · ')}
                        {b.aliases.length > 3 ? ` …+${b.aliases.length - 3}` : ''}
                      </span>
                    )}
                  </td>
                  <td>
                    {/* 这张表只剩监测对象之后，「没配竞品」就从常态变成了异常 ——
                        缺口清单和失分量都要靠竞品集才算得出来。所以它现在值得说话，
                        而不是像以前那样 15/17 行都是一个淡破折号。 */}
                    {b.competitor_ids.length === 0 ? (
                      <span style={{ color: 'var(--warn)', fontSize: 'var(--fs-label)' }}>
                        未配竞品
                      </span>
                    ) : (
                      <span
                        style={{ fontSize: 'var(--fs-label)', color: 'var(--text-2)' }}
                        title={b.competitor_ids
                          .map((id) => brands.find((x) => x.id === id)?.name ?? `#${id}`)
                          .join(' · ')}
                      >
                        {b.competitor_ids.length} 个
                      </span>
                    )}
                  </td>
                  <td>
                    {/* 品牌 → 任务这条路以前是断的（只有一个数字，点不动） */}
                    {taskCount === 0 ? (
                      <span style={{ color: 'var(--text-3)', fontSize: 'var(--fs-label)' }}>
                        还没建
                      </span>
                    ) : (
                      <Link href={`/tasks?brand=${b.id}`} className={kit.rowLink}>
                        {taskCount} 个
                      </Link>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Plate>
    </div>
  )
}
