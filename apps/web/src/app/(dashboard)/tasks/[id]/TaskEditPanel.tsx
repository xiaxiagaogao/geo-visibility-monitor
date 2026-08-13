'use client'

import { useEffect, useState } from 'react'

import { Badge, Button, ErrorState, Panel, PanelNote, Skeleton, ui } from '@/components/ui'
import { ApiError } from '@/lib/api/client'
import { fetchPlatforms } from '@/lib/api/config'
import { updateTask } from '@/lib/api/tasks'
import type { PlatformOption, Task } from '@/lib/types'

/**
 * 任务编辑（P2-02）。
 *
 * `PATCH /v1/tasks/{id}` 一直都有，只是界面上一个入口都没有 ——
 * 任务建完只能看，改名 / 换平台 / 改采样数全都做不了。
 *
 * 三条语义写进了界面：
 *
 *   1. **没有品牌这一项。** 后端 `TaskUpdate` 里就没有 `brand_id` —— 任务过不了户。
 *      放一个改不动的下拉框只会让人以为改得动。
 *   2. **改平台 / 采样数只影响以后。** 每次 run 都有自己的 platforms 快照，
 *      历史运行不会被改写 —— 这正是快照存在的理由。
 *   3. **停用之后发起运行会被拒**（400）。这一条在 2026-08-12 之前不成立：
 *      当时 `start_run` 不看 `is_active`，「已停用」只是个徽章。
 */
export function TaskEditPanel({
  task,
  onSaved,
  onCancel,
}: {
  task: Task
  onSaved: () => void
  onCancel: () => void
}) {
  const [platforms, setPlatforms] = useState<PlatformOption[] | null>(null)
  const [loadError, setLoadError] = useState<Error | null>(null)

  const [name, setName] = useState(task.name)
  const [picked, setPicked] = useState<string[]>(task.platforms)
  const [samples, setSamples] = useState(task.samples)
  const [isActive, setIsActive] = useState(task.is_active)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    // 平台清单读 /v1/config/platforms，不硬编码（API.md §5）
    fetchPlatforms()
      .then((p) => {
        if (alive) setPlatforms(p.items)
      })
      .catch((e: unknown) => {
        if (alive) setLoadError(e instanceof Error ? e : new Error(String(e)))
      })
    return () => {
      alive = false
    }
  }, [])

  const dirty =
    name !== task.name ||
    samples !== task.samples ||
    isActive !== task.is_active ||
    picked.length !== task.platforms.length ||
    picked.some((c, i) => c !== task.platforms[i])

  async function save() {
    setBusy(true)
    setErr(null)
    try {
      await updateTask(task.id, {
        name: name.trim(),
        platforms: picked,
        samples,
        is_active: isActive,
      })
      onSaved()
    } catch (e) {
      // 400 常见于「平台没接」——后端会连可用清单一起返回，原样显示
      setErr(e instanceof ApiError ? e.detail : '保存失败')
      setBusy(false)
    }
  }

  if (loadError) {
    return (
      <Panel title="编辑任务">
        <ErrorState
          status={loadError instanceof ApiError ? loadError.status : 0}
          message={loadError instanceof ApiError ? loadError.detail : '加载失败'}
        />
      </Panel>
    )
  }

  return (
    <Panel
      title="编辑任务"
      subtitle="品牌不在这里 —— 任务过不了户，后端也不收这个字段"
      right={<Button onClick={onCancel}>取消</Button>}
    >
      <div className={ui.formGrid}>
        <label className={ui.field}>
          <span className={ui.fieldLabel}>任务名</span>
          <input
            className={ui.input}
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={120}
            disabled={busy}
          />
        </label>

        <div className={ui.field}>
          <span className={ui.fieldLabel}>平台</span>
          {platforms === null ? (
            <Skeleton height={28} width="60%" />
          ) : (
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {platforms.map((p) => (
                <button
                  key={p.code}
                  type="button"
                  className={`${ui.chip} ${picked.includes(p.code) ? ui.chipOn : ''}`}
                  onClick={() =>
                    setPicked((prev) =>
                      prev.includes(p.code)
                        ? prev.filter((c) => c !== p.code)
                        : [...prev, p.code],
                    )
                  }
                  // 建完就跑不了的平台不给选 —— 否则用户看到的是「抓取失败」，
                  // 而真相是「这个平台没接」
                  disabled={(!p.available && !picked.includes(p.code)) || busy}
                  title={p.available ? undefined : (p.note ?? '该平台尚未接入')}
                >
                  {p.label}
                  {p.available ? '' : ' · 未接入'}
                </button>
              ))}
            </div>
          )}
        </div>

        <label className={ui.field} style={{ maxWidth: 200 }}>
          <span className={ui.fieldLabel}>每条提问采样次数</span>
          <input
            className={ui.input}
            type="number"
            min={1}
            max={20}
            value={samples}
            onChange={(e) => setSamples(Number(e.target.value))}
            disabled={busy}
          />
        </label>

        <label style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <input
            type="checkbox"
            checked={!isActive}
            onChange={(e) => setIsActive(!e.target.checked)}
            disabled={busy}
          />
          <span className={ui.fieldLabel}>停用这个任务</span>
          {!isActive ? <Badge tone="warning">已停用</Badge> : null}
        </label>

        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <Button primary onClick={save} disabled={!dirty || busy || !name.trim() || !picked.length}>
            {busy ? '保存中…' : '保存'}
          </Button>
          {dirty ? (
            <span style={{ fontSize: 'var(--fs-xs)', color: 'var(--warning)' }}>
              有未保存的改动
            </span>
          ) : null}
        </div>

        {err ? (
          <p role="alert" style={{ color: 'var(--danger)', fontSize: 'var(--fs-xs)' }}>
            {err}
          </p>
        ) : null}
      </div>

      <PanelNote>
        改平台与采样数<strong>只影响以后的运行</strong> —— 每次 run 都冻结了自己那份
        平台快照，历史运行不会被改写。
        <br />
        <strong>停用之后发起运行会被拒绝</strong>，但已有的运行与证据都留着。
      </PanelNote>
    </Panel>
  )
}
