'use client'

import Link from 'next/link'
import { useCallback, useEffect, useState } from 'react'

import { Mark, Blank, Fault, PageHead, Plate, Pending, Table, kit } from '@/components/kit'
import { canWrite } from '@/lib/api/auth'
import { listBrands } from '@/lib/api/brands'
import { ApiError } from '@/lib/api/client'
import { useAuth } from '@/lib/auth-context'
import type { Brand } from '@/lib/types'

/**
 * 品牌列表（A2）。
 *
 * **`workspace_id` 单独占一列，不是凑数。** 它决定哪些客户账号能看到这个品牌，
 * 而且**建完就改不了**（`BrandUpdate` 里没有这个字段）。把它藏起来的话，
 * 建错 workspace 只能删了重建 —— 而删品牌是级联删除。
 */
export function BrandsView() {
  const { me } = useAuth()
  const [brands, setBrands] = useState<Brand[] | null>(null)
  const [error, setError] = useState<Error | null>(null)

  const load = useCallback(() => {
    setError(null)
    setBrands(null)
    listBrands()
      .then((b) => setBrands(b.items))
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

  // 竞品名要靠 id 关联 —— 列表里显示「比了几个」时也一样，
  // 不能拿数组下标当身份
  const nameOf = (id: number) => brands?.find((b) => b.id === id)?.name ?? `#${id}`

  return (
    <div className={kit.pageStack}>
      <PageHead
        title="品牌"
        lede="别名决定 L1 能不能认出它；竞品集决定缺口清单和失分量跟谁比。"
        action={
          canWrite(me) ? (
            <Link href="/brands/new" className={kit.link}>
              新建品牌 +
            </Link>
          ) : null
        }
      />

      <Plate>
      {brands === null ? (
        <div style={{ display: 'grid', gap: 8 }}>
          <Pending height={20} />
          <Pending height={20} />
        </div>
      ) : brands.length === 0 ? (
        <Blank lead="还没有品牌">
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
            </tr>
          </thead>
          <tbody>
            {brands.map((b) => (
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
                  {b.competitor_ids.length === 0 ? (
                    <Mark>无</Mark>
                  ) : (
                    <span
                      style={{ fontSize: 'var(--fs-label)', color: 'var(--text-2)' }}
                      title={b.competitor_ids.map(nameOf).join(' · ')}
                    >
                      {b.competitor_ids.length} 个
                    </span>
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
