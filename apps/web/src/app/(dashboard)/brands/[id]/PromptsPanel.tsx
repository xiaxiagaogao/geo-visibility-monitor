'use client'

import { useCallback, useEffect, useState, type FormEvent } from 'react'

import {
  Mark,
  Button,
  Blank,
  Fault,
  Plate,
  Aside,
  Pending,
  kit,
} from '@/components/kit'
import { ApiError } from '@/lib/api/client'
import { createPrompt, deletePrompt, listPrompts, updatePrompt } from '@/lib/api/prompts'
import { activeCount, groupByCategory } from '@/lib/l3/prompts'
import type { Prompt } from '@/lib/types'

import styles from '../brands.module.css'

/** 后端没有类别枚举接口，这里只作为输入建议，不限制取值（API.md §6） */
const CATEGORY_SUGGESTIONS = ['unprompted', 'scenario']

/**
 * 提问词管理（A3）。挂在品牌详情页里 —— 提问词属于品牌，不该另起一个路由。
 *
 * **这一页最重要的一件事是把「停用」和「删除」分开。** 它们看起来都是
 * 「以后不问这条了」，后果差一个数量级：
 *
 *   · 停用（`is_active=false`）：只影响未来的 run。`create_run` 只冻结
 *     启用中的提问词，历史一个数字都不动。
 *   · 删除：`crawl_jobs.prompt_id` 是 ON DELETE CASCADE，会连带删掉这条
 *     提问词的全部 job → response → mention。**历史 run 的数会当场变** ——
 *     快照行还在（`run_prompts.prompt_id` 没有外键，这是刻意的），
 *     但那一行的 n 掉到 0，整个 run 的 n_valid 少一截，总提及率跟着变。
 *
 * 所以停用是行内的常规操作，删除藏在二次确认后面并写明后果。
 */
export function PromptsPanel({
  brandId,
  writable,
}: {
  brandId: number
  writable: boolean
}) {
  const [prompts, setPrompts] = useState<Prompt[] | null>(null)
  const [error, setError] = useState<Error | null>(null)
  const [reloadKey, setReloadKey] = useState(0)

  const reload = useCallback(() => setReloadKey((k) => k + 1), [])

  useEffect(() => {
    let alive = true
    setError(null)
    // 不传 activeOnly —— 管理界面要看得见停用的那些，
    // 否则用户会以为它们被删了
    listPrompts({ brandId })
      .then((r) => {
        if (alive) setPrompts(r.items)
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
      <Plate title="提问词">
        <Fault
          status={error instanceof ApiError ? error.status : 0}
          message={error instanceof ApiError ? error.detail : '加载失败'}
          onRetry={reload}
        />
      </Plate>
    )
  }

  if (prompts === null) {
    return (
      <Plate title="提问词">
        <div style={{ display: 'grid', gap: 8 }}>
          <Pending height={20} />
          <Pending height={20} />
        </div>
      </Plate>
    )
  }

  const active = activeCount(prompts)
  const groups = groupByCategory(prompts)

  return (
    <Plate
      title="提问词"
      subtitle="这些问题会被拿去问 AI。启用中的条数 × 采样数 = 一次运行建出来的 job 数"
      right={
        <span style={{ fontSize: 'var(--fs-label)', color: 'var(--text-3)' }}>
          共 {prompts.length} 条 · 启用 {active} 条
        </span>
      }
    >
      {/* 提及率的分母就是这些提问跑出来的样本数。全停用的话下一次运行会是
          `empty` —— 一条 job 都建不出来，那是配置问题不是采集失败 */}
      {active === 0 ? (
        <Aside>
          <strong style={{ color: 'var(--down)' }}>一条启用中的提问词都没有。</strong>
          现在发起运行会建不出任何 job，run 状态是「未产生任务」——
          那是配置问题，不是采集失败。
        </Aside>
      ) : null}

      {prompts.length === 0 ? (
        <Blank lead="还没有提问词">
          {writable
            ? '加几条你想知道 AI 会怎么回答的问题。它们是这个品牌全部数据的来源。'
            : '还没有为这个品牌配置提问词。'}
        </Blank>
      ) : (
        groups.map((g) => (
          <div key={g.category} style={{ marginBottom: 'var(--sp-4)' }}>
            <div className={styles.groupHead}>
              {g.label}
              <span className={styles.groupCount}>{g.prompts.length}</span>
            </div>
            {g.prompts.map((p) => (
              <PromptRow key={p.id} prompt={p} writable={writable} onChanged={reload} />
            ))}
          </div>
        ))
      )}

      {writable ? <AddPromptForm brandId={brandId} onAdded={reload} /> : null}
    </Plate>
  )
}

/* ══════ 一行 ══════ */

function PromptRow({
  prompt,
  writable,
  onChanged,
}: {
  prompt: Prompt
  writable: boolean
  onChanged: () => void
}) {
  const [editing, setEditing] = useState(false)
  const [text, setText] = useState(prompt.text)
  const [busy, setBusy] = useState(false)
  const [armed, setArmed] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  async function run(fn: () => Promise<unknown>) {
    setBusy(true)
    setErr(null)
    try {
      await fn()
      onChanged()
    } catch (e) {
      setErr(e instanceof ApiError ? e.detail : '操作失败')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className={`${styles.promptRow} ${prompt.is_active ? '' : styles.promptOff}`}>
      <div style={{ flex: 1, minWidth: 0 }}>
        {editing ? (
          <input
            className={kit.input}
            value={text}
            onChange={(e) => setText(e.target.value)}
            disabled={busy}
            autoFocus
          />
        ) : (
          <div className={styles.promptText}>{prompt.text}</div>
        )}
        {err ? (
          <div role="alert" style={{ color: 'var(--down)', fontSize: 'var(--fs-label)' }}>
            {err}
          </div>
        ) : null}
        {armed ? (
          <div className={kit.deleteWarn} role="alert">
            <strong style={{ color: 'var(--down)' }}>删除会改写历史，不只是「以后不问」。</strong>
            它的全部采样、回答与标注会一起删掉，用过这条提问的<strong>历史运行</strong>
            分母会少一截，总提及率当场变。
            <br />
            只是想以后不再问它 → 点<strong>停用</strong>，历史一个数字都不动。
          </div>
        ) : null}
      </div>

      {!prompt.is_active ? <Mark>已停用</Mark> : null}

      {writable ? (
        <div className={styles.promptActions}>
          {editing ? (
            <>
              <Button
                primary
                onClick={() => run(async () => {
                  await updatePrompt(prompt.id, { text: text.trim() })
                  setEditing(false)
                })}
                disabled={busy || !text.trim() || text.trim() === prompt.text}
              >
                {busy ? '保存中…' : '保存'}
              </Button>
              <Button
                onClick={() => {
                  setText(prompt.text)
                  setEditing(false)
                }}
                disabled={busy}
              >
                取消
              </Button>
            </>
          ) : armed ? (
            <>
              <Button
                primary
                onClick={() => run(() => deletePrompt(prompt.id))}
                disabled={busy}
              >
                {busy ? '删除中…' : '确认删除'}
              </Button>
              <Button onClick={() => setArmed(false)} disabled={busy}>
                取消
              </Button>
            </>
          ) : (
            <>
              <Button onClick={() => setEditing(true)} disabled={busy}>
                改
              </Button>
              {/* 停用是常规操作，摆在外面；删除要多点一下 */}
              <Button
                onClick={() => run(() => updatePrompt(prompt.id, { is_active: !prompt.is_active }))}
                disabled={busy}
              >
                {prompt.is_active ? '停用' : '启用'}
              </Button>
              <Button onClick={() => setArmed(true)} disabled={busy}>
                删除
              </Button>
            </>
          )}
        </div>
      ) : null}
    </div>
  )
}

/* ══════ 新增 ══════ */

function AddPromptForm({ brandId, onAdded }: { brandId: number; onAdded: () => void }) {
  const [text, setText] = useState('')
  const [category, setCategory] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setErr(null)
    try {
      await createPrompt({
        brand_id: brandId,
        text: text.trim(),
        category: category.trim() || null,
      })
      setText('')
      setCategory('')
      onAdded()
    } catch (e2) {
      setErr(e2 instanceof ApiError ? e2.detail : '添加失败')
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={onSubmit} className={styles.addRow}>
      <input
        className={kit.input}
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="例：2026年跑步鞋哪个品牌好？"
        disabled={busy}
        required
        style={{ flex: 1, minWidth: 220 }}
      />
      <input
        className={kit.input}
        value={category}
        onChange={(e) => setCategory(e.target.value)}
        placeholder="类别（可选）"
        list="prompt-categories"
        disabled={busy}
        style={{ width: 150 }}
      />
      {/* 用 datalist 而不是 select：后端对 category 没有枚举约束，
          做成下拉框等于在前端凭空发明一套后端不认的取值 */}
      <datalist id="prompt-categories">
        {CATEGORY_SUGGESTIONS.map((c) => (
          <option key={c} value={c} />
        ))}
      </datalist>
      <Button type="submit" primary disabled={busy || !text.trim()}>
        {busy ? '添加中…' : '添加'}
      </Button>
      {err ? (
        <span role="alert" style={{ color: 'var(--down)', fontSize: 'var(--fs-label)' }}>
          {err}
        </span>
      ) : null}
    </form>
  )
}
