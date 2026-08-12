'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useCallback, useEffect, useState } from 'react'

import runs from '@/components/runs/runs.module.css'
import {
  Badge,
  Button,
  EmptyState,
  ErrorState,
  Panel,
  PanelNote,
  Skeleton,
  ui,
} from '@/components/ui'
import { canWrite } from '@/lib/api/auth'
import {
  deleteBrand,
  getBrand,
  listBrands,
  replaceAliases,
  replaceCompetitors,
  updateBrand,
} from '@/lib/api/brands'
import { ApiError } from '@/lib/api/client'
import { listTasks } from '@/lib/api/tasks'
import { useAuth } from '@/lib/auth-context'
import {
  formatAliasLines,
  parseAliasLines,
  sameList,
  sanitizeCompetitorIds,
  toggleCompetitor,
} from '@/lib/l3/brands'
import type { Brand } from '@/lib/types'

import { PromptsPanel } from './PromptsPanel'

import styles from '../brands.module.css'

/**
 * 品牌详情（A2）：基本信息 · 别名 · 竞品 · 删除。
 *
 * **三块各自独立保存**，因为它们是三个不同的接口，语义也不同：
 * 基本信息是 PATCH（增量），别名与竞品是 PUT（**整体替换**）。
 * 做成一个「保存」按钮会把三种语义糊成一种，而糊掉的那两种正是危险的那两种。
 */
export function BrandDetailView({ brandId }: { brandId: number }) {
  const { me } = useAuth()
  const [brand, setBrand] = useState<Brand | null>(null)
  const [allBrands, setAllBrands] = useState<Brand[]>([])
  const [taskCount, setTaskCount] = useState<number | null>(null)
  const [error, setError] = useState<Error | null>(null)
  const [reloadKey, setReloadKey] = useState(0)

  const reload = useCallback(() => setReloadKey((k) => k + 1), [])

  useEffect(() => {
    let alive = true
    setError(null)
    // **不清 brand。** 保存后的重取要让旧数据继续显示，否则三个面板会一起
    // 卸载重挂，「已保存」提示当场没了。换品牌由路由层的 key 负责重挂。
    Promise.all([getBrand(brandId), listBrands(), listTasks({ brandId })])
      .then(([b, all, tasks]) => {
        if (!alive) return
        setBrand(b)
        setAllBrands(all.items)
        setTaskCount(tasks.total)
      })
      .catch((e: unknown) => {
        if (alive) setError(e instanceof Error ? e : new Error(String(e)))
      })
    return () => {
      alive = false
    }
  }, [brandId, reloadKey])

  if (error) {
    return (
      <ErrorState
        status={error instanceof ApiError ? error.status : 0}
        message={
          error instanceof ApiError && error.status === 404
            ? '没有这个品牌，或它不在你的可见范围内'
            : error instanceof ApiError
              ? error.detail
              : '加载失败'
        }
        onRetry={reload}
      />
    )
  }

  if (!brand) {
    return (
      <div style={{ display: 'grid', gap: 12 }}>
        <Skeleton height={28} width="40%" />
        <Skeleton height={180} />
      </div>
    )
  }

  const writable = canWrite(me)

  return (
    <div className={runs.panelStack}>
      <div className={runs.taskHead}>
        <div>
          <h1 className={runs.taskTitle}>
            {brand.name}
            {brand.name_en ? <Badge>{brand.name_en}</Badge> : null}
          </h1>
          <div className={runs.taskMeta}>
            <span>{brand.industry || '未填行业'}</span>
            <span>·</span>
            <span className={ui.numeric}>workspace {brand.workspace_id}</span>
            <span>·</span>
            <span>{taskCount === null ? '—' : `${taskCount} 个任务`}</span>
          </div>
        </div>
        <Link href="/brands" className={ui.rowLink}>
          ← 品牌列表
        </Link>
      </div>

      <BasicPanel brand={brand} writable={writable} onSaved={reload} />
      <AliasPanel brand={brand} writable={writable} onSaved={reload} />
      <CompetitorPanel
        brand={brand}
        allBrands={allBrands}
        writable={writable}
        onSaved={reload}
      />

      <PromptsPanel brandId={brand.id} writable={writable} />

      {writable ? <DangerPanel brand={brand} taskCount={taskCount} /> : null}
    </div>
  )
}

/* ══════ 基本信息（PATCH，增量）══════ */

function BasicPanel({
  brand,
  writable,
  onSaved,
}: {
  brand: Brand
  writable: boolean
  onSaved: () => void
}) {
  const [name, setName] = useState(brand.name)
  const [nameEn, setNameEn] = useState(brand.name_en ?? '')
  const [industry, setIndustry] = useState(brand.industry ?? '')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [ok, setOk] = useState(false)

  const dirty =
    name !== brand.name ||
    nameEn !== (brand.name_en ?? '') ||
    industry !== (brand.industry ?? '')

  async function save() {
    setBusy(true)
    setErr(null)
    setOk(false)
    try {
      await updateBrand(brand.id, {
        name: name.trim(),
        name_en: nameEn.trim() || null,
        industry: industry.trim() || null,
      })
      setOk(true)
      onSaved()
    } catch (e) {
      setErr(e instanceof ApiError ? e.detail : '保存失败')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Panel title="基本信息">
      <div className={ui.formGrid}>
        <label className={ui.field}>
          <span className={ui.fieldLabel}>品牌名</span>
          <input
            className={ui.input}
            value={name}
            onChange={(e) => setName(e.target.value)}
            disabled={!writable || busy}
            maxLength={200}
          />
        </label>
        <label className={ui.field}>
          <span className={ui.fieldLabel}>英文名</span>
          <input
            className={ui.input}
            value={nameEn}
            onChange={(e) => setNameEn(e.target.value)}
            disabled={!writable || busy}
          />
        </label>
        <label className={ui.field}>
          <span className={ui.fieldLabel}>行业</span>
          <input
            className={ui.input}
            value={industry}
            onChange={(e) => setIndustry(e.target.value)}
            disabled={!writable || busy}
          />
        </label>

        {/* workspace_id 只读展示，不给编辑框 —— 后端 BrandUpdate 里根本没有
            这个字段，做个输入框在这儿只会让人以为改得动 */}
        <div className={ui.field}>
          <span className={ui.fieldLabel}>workspace_id</span>
          <div className={ui.numeric} style={{ fontSize: 'var(--fs-body)' }}>
            {brand.workspace_id}
            <span style={{ marginLeft: 8, fontSize: 'var(--fs-xs)', color: 'var(--text-tertiary)' }}>
              不可修改 —— 品牌不能换 workspace
            </span>
          </div>
        </div>
      </div>

      {writable ? (
        <SaveBar
          dirty={dirty}
          busy={busy}
          ok={ok}
          err={err}
          onSave={save}
          disabled={!name.trim()}
        />
      ) : null}
    </Panel>
  )
}

/* ══════ 别名（PUT，整体替换）══════ */

function AliasPanel({
  brand,
  writable,
  onSaved,
}: {
  brand: Brand
  writable: boolean
  onSaved: () => void
}) {
  const [text, setText] = useState(formatAliasLines(brand.aliases))
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [ok, setOk] = useState(false)

  const next = parseAliasLines(text)
  const dirty = !sameList(next, brand.aliases)

  async function save() {
    setBusy(true)
    setErr(null)
    setOk(false)
    try {
      // 提交的是**整份列表**，不是新增的那些 —— 这就是 PUT 的语义
      await replaceAliases(brand.id, next)
      setOk(true)
      onSaved()
    } catch (e) {
      setErr(e instanceof ApiError ? e.detail : '保存失败')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Panel
      title="别名"
      subtitle="L1 靠这些词在回答正文里认出这个品牌。少一个常用写法，就会漏检成「未提及」"
    >
      <textarea
        className={styles.aliasBox}
        value={text}
        onChange={(e) => setText(e.target.value)}
        disabled={!writable || busy}
        placeholder={'一行一个\nANTA\n安踏体育'}
      />
      <PanelNote>
        <strong>整体替换。</strong>保存时提交的是文本框里的全部内容 ——
        删掉一行就是删掉那个别名。这也意味着清空文本框再保存 = 删光所有别名。
        {brand.aliases.length > 0 ? `当前 ${brand.aliases.length} 个。` : ''}
      </PanelNote>
      {writable ? (
        <SaveBar dirty={dirty} busy={busy} ok={ok} err={err} onSave={save} />
      ) : null}
    </Panel>
  )
}

/* ══════ 竞品（PUT，整体替换）══════ */

function CompetitorPanel({
  brand,
  allBrands,
  writable,
  onSaved,
}: {
  brand: Brand
  allBrands: Brand[]
  writable: boolean
  onSaved: () => void
}) {
  const [ids, setIds] = useState<number[]>(brand.competitor_ids)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [ok, setOk] = useState(false)

  const others = allBrands.filter((b) => b.id !== brand.id)
  const nameOf = (id: number) => allBrands.find((b) => b.id === id)?.name ?? `#${id}`
  const dirty = !sameList(ids, brand.competitor_ids)

  async function save() {
    setBusy(true)
    setErr(null)
    setOk(false)
    try {
      // 前端先按后端的三条规则清一遍（不能是自己 · 去重 · 必须存在），
      // 免得点了保存才收到 400
      const clean = sanitizeCompetitorIds(
        ids,
        brand.id,
        allBrands.map((b) => b.id),
      )
      await replaceCompetitors(brand.id, clean)
      setOk(true)
      onSaved()
    } catch (e) {
      setErr(e instanceof ApiError ? e.detail : '保存失败')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Panel
      title="竞品"
      subtitle="缺口清单与失分量跟谁比，由这一组决定。列表顺序就是命中矩阵的列顺序"
    >
      {/* 已选的按顺序摆出来 —— 顺序是矩阵列顺序的唯一依据，藏在勾选框里看不出来 */}
      <div className={styles.orderStrip}>
        {ids.length === 0 ? (
          <span style={{ fontSize: 'var(--fs-xs)', color: 'var(--text-tertiary)' }}>
            还没选竞品 —— 缺口清单会永远是空的（没有竞品在场，就判不出缺口）
          </span>
        ) : (
          ids.map((id, i) => (
            <span key={id} className={styles.orderChip}>
              <span className={styles.orderNum}>{i + 1}</span>
              {nameOf(id)}
              {writable ? (
                <button
                  type="button"
                  className={styles.chipX}
                  onClick={() => setIds(toggleCompetitor(ids, id))}
                  aria-label={`移除 ${nameOf(id)}`}
                  disabled={busy}
                >
                  ×
                </button>
              ) : null}
            </span>
          ))
        )}
      </div>

      {others.length === 0 ? (
        <EmptyState>
          <strong style={{ color: 'var(--text-secondary)' }}>没有别的品牌可选</strong>
          <span>竞品也是品牌行，不是字符串 —— 先把竞品当作品牌建出来。</span>
        </EmptyState>
      ) : (
        <div className={styles.pickGrid}>
          {others.map((b) => (
            <label key={b.id} className={styles.pickItem}>
              <input
                type="checkbox"
                checked={ids.includes(b.id)}
                onChange={() => setIds(toggleCompetitor(ids, b.id))}
                disabled={!writable || busy}
              />
              {b.name}
            </label>
          ))}
        </div>
      )}

      <PanelNote>
        <strong>整体替换，且只影响以后。</strong>竞品集在发起 run 的那一刻被冻结进快照，
        改它<strong>不会</strong>回头改写历史运行的缺口清单 —— 那正是 <span className="mono">run_competitors</span> 存在的理由。
        但下一次运行会按新的这一组算。
      </PanelNote>

      {writable ? (
        <SaveBar dirty={dirty} busy={busy} ok={ok} err={err} onSave={save} />
      ) : null}
    </Panel>
  )
}

/* ══════ 危险区 ══════ */

function DangerPanel({ brand, taskCount }: { brand: Brand; taskCount: number | null }) {
  const router = useRouter()
  const [armed, setArmed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  async function doDelete() {
    setBusy(true)
    setErr(null)
    try {
      await deleteBrand(brand.id)
      router.replace('/brands')
    } catch (e) {
      setErr(e instanceof ApiError ? e.detail : '删除失败')
      setBusy(false)
    }
  }

  return (
    <div className={styles.dangerZone}>
      <p className={styles.dangerText}>
        <strong style={{ color: 'var(--danger)' }}>删除品牌</strong>
        {' —— '}
        会<strong>级联删掉</strong>它的提问词、别名、竞品关系，以及挂在它下面的任务、
        运行与证据。
        {taskCount !== null && taskCount > 0 ? (
          <>
            {' '}
            这个品牌下现在有 <strong>{taskCount} 个任务</strong>，它们的历史运行会一起没。
          </>
        ) : null}
        {' '}这个操作不可撤销，也没有回收站。
      </p>

      {!armed ? (
        <Button onClick={() => setArmed(true)}>删除这个品牌</Button>
      ) : (
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <span style={{ fontSize: 'var(--fs-xs)', color: 'var(--danger)' }}>
            确认删除「{brand.name}」？
          </span>
          <Button primary onClick={doDelete} disabled={busy}>
            {busy ? '删除中…' : '确认删除'}
          </Button>
          <Button onClick={() => setArmed(false)} disabled={busy}>
            取消
          </Button>
        </div>
      )}

      {err ? (
        <p role="alert" style={{ color: 'var(--danger)', fontSize: 'var(--fs-xs)', marginTop: 8 }}>
          {err}
        </p>
      ) : null}
    </div>
  )
}

/* ══════ 保存条 ══════ */

function SaveBar({
  dirty,
  busy,
  ok,
  err,
  onSave,
  disabled,
}: {
  dirty: boolean
  busy: boolean
  ok: boolean
  err: string | null
  onSave: () => void
  disabled?: boolean
}) {
  return (
    <div className={styles.saveBar}>
      <Button primary onClick={onSave} disabled={!dirty || busy || disabled}>
        {busy ? '保存中…' : '保存'}
      </Button>
      {/* 「有未保存的改动」要说出来 —— 三块各自独立保存，
          改了一块去改另一块很容易忘了前一块没提交 */}
      {dirty ? <span className={styles.dirty}>有未保存的改动</span> : null}
      {!dirty && ok ? <span className={styles.saved}>已保存</span> : null}
      {err ? (
        <span role="alert" style={{ color: 'var(--danger)', fontSize: 'var(--fs-xs)' }}>
          {err}
        </span>
      ) : null}
    </div>
  )
}
