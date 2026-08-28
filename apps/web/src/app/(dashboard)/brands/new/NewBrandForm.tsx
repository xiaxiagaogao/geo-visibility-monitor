'use client'

import { useRouter } from 'next/navigation'
import { useState, type FormEvent } from 'react'

import { Button, Plate, Aside, kit } from '@/components/kit'
import { createBrand } from '@/lib/api/brands'
import { ApiError } from '@/lib/api/client'
import { parseAliasLines } from '@/lib/l3/brands'

import styles from '../brands.module.css'

/**
 * 新建品牌（A2）。
 *
 * **`workspace_id` 摆在表单里，而且是必须想清楚的一项** ——
 * `BrandUpdate` 里没有这个字段，建完就改不了。填错只能删了重建，
 * 而删品牌是级联删除（连提问词、竞品关系、标注一起没）。
 *
 * 竞品不在这里配：它要从**已存在的品牌**里挑，而这个品牌此刻还不存在。
 * 建完落到详情页再配，那里能看到全量品牌列表。
 */
export function NewBrandForm() {
  const router = useRouter()
  const [name, setName] = useState('')
  const [nameEn, setNameEn] = useState('')
  const [industry, setIndustry] = useState('')
  const [workspaceId, setWorkspaceId] = useState(1)
  const [aliasText, setAliasText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      const brand = await createBrand({
        name: name.trim(),
        name_en: nameEn.trim() || null,
        industry: industry.trim() || null,
        workspace_id: workspaceId,
        // 前端先归一化一遍，让「保存后长什么样」在提交前就是确定的
        aliases: parseAliasLines(aliasText),
      })
      router.replace(`/brands/${brand.id}`)
    } catch (err) {
      // 403 **不跳登录** —— 用户是登着的，跳了会陷入死循环
      setError(err instanceof ApiError ? err.detail : '创建失败，请稍后重试')
      setBusy(false)
    }
  }

  return (
    <form onSubmit={onSubmit}>
      <Plate title="新建品牌" subtitle="别名决定 L1 能不能认出它；竞品建完之后在详情页配">
        <div className={kit.formGrid}>
          <label className={kit.field}>
            <span className={kit.fieldLabel}>品牌名</span>
            <input
              className={kit.input}
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="例：安踏"
              maxLength={200}
              disabled={busy}
              required
            />
          </label>

          <label className={kit.field}>
            <span className={kit.fieldLabel}>英文名（可选）</span>
            <input
              className={kit.input}
              value={nameEn}
              onChange={(e) => setNameEn(e.target.value)}
              placeholder="ANTA"
              disabled={busy}
            />
          </label>

          <label className={kit.field}>
            <span className={kit.fieldLabel}>行业（可选）</span>
            <input
              className={kit.input}
              value={industry}
              onChange={(e) => setIndustry(e.target.value)}
              placeholder="运动鞋服"
              disabled={busy}
            />
          </label>

          <label className={kit.field}>
            <span className={kit.fieldLabel}>workspace_id</span>
            <input
              className={kit.input}
              type="number"
              min={1}
              value={workspaceId}
              onChange={(e) => setWorkspaceId(Number(e.target.value))}
              disabled={busy}
              required
              style={{ maxWidth: 160 }}
            />
            <span style={{ fontSize: 'var(--fs-label)', color: 'var(--down)' }}>
              建完改不了。它决定哪些客户账号能看到这个品牌 —— 客户只能看到
              自己 workspace 下的品牌，填错只能删了重建。
            </span>
          </label>

          <label className={kit.field}>
            <span className={kit.fieldLabel}>别名（一行一个，可选）</span>
            <textarea
              className={styles.aliasBox}
              value={aliasText}
              onChange={(e) => setAliasText(e.target.value)}
              placeholder={'ANTA\n安踏体育'}
              disabled={busy}
            />
            <span style={{ fontSize: 'var(--fs-label)', color: 'var(--text-3)' }}>
              空行会被忽略；大小写不同的同一个词只留第一次出现的写法。
            </span>
          </label>

          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <Button type="submit" primary disabled={busy}>
              {busy ? '创建中…' : '创建品牌'}
            </Button>
            <Button onClick={() => router.back()} disabled={busy}>
              取消
            </Button>
          </div>

          {error ? (
            <p role="alert" style={{ color: 'var(--down)', fontSize: 'var(--fs-label)' }}>
              {error}
            </p>
          ) : null}
        </div>
      </Plate>

      <Aside>
        建品牌<strong>不会</strong>产生任何监测。要跑起来还得给它配提问词、
        建一个任务、再发起运行。
      </Aside>
    </form>
  )
}
