'use client'

import { useRouter } from 'next/navigation'
import { useEffect, useState, type FormEvent } from 'react'

import { Mark, Button, Fault, Plate, Aside, Pending, kit } from '@/components/kit'
import { listBrands } from '@/lib/api/brands'
import { ApiError } from '@/lib/api/client'
import { fetchPlatforms } from '@/lib/api/config'
import { createTask } from '@/lib/api/tasks'
import type { Brand, PlatformOption } from '@/lib/types'

/**
 * 新建任务。
 *
 * **平台清单读 `/v1/config/platforms`，不硬编码**（API.md §5）——
 * 接第二个平台时后端改一行，这里零改动。`available=false` 的灰显不可选：
 * 让人选一个建完就跑不了的平台，等于把「抓取失败」这个假象做进 UI。
 *
 * 这是前端第一个真实写操作，也是 CSRF 链路的验证点：`apiFetch` 对
 * POST 无条件带 `X-CSRF-Token`，后端开关已打开，带错或不带都会 403。
 */
export function NewTaskForm() {
  const router = useRouter()
  const [brands, setBrands] = useState<Brand[] | null>(null)
  const [platforms, setPlatforms] = useState<PlatformOption[] | null>(null)
  const [crawlMode, setCrawlMode] = useState<string>('')
  const [loadError, setLoadError] = useState<Error | null>(null)

  const [brandId, setBrandId] = useState<number | ''>('')
  const [name, setName] = useState('')
  const [picked, setPicked] = useState<string[]>([])
  const [samples, setSamples] = useState(3)
  const [busy, setBusy] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([listBrands(), fetchPlatforms()])
      .then(([b, p]) => {
        setBrands(b.items)
        setPlatforms(p.items)
        setCrawlMode(p.crawl_mode)
        // 只有一个品牌时直接选上，省一次点击
        if (b.items.length === 1) setBrandId(b.items[0].id)
      })
      .catch((e: unknown) => setLoadError(e instanceof Error ? e : new Error(String(e))))
  }, [])

  function togglePlatform(code: string) {
    setPicked((prev) => (prev.includes(code) ? prev.filter((c) => c !== code) : [...prev, code]))
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setSubmitError(null)
    if (brandId === '' || picked.length === 0) {
      setSubmitError('请选择品牌与至少一个平台')
      return
    }
    setBusy(true)
    try {
      const task = await createTask({
        brand_id: brandId,
        name: name.trim(),
        platforms: picked,
        samples,
      })
      router.replace(`/tasks/${task.id}`)
    } catch (err) {
      // 403 在这里**不跳登录** —— 用户是登着的，跳了会陷入死循环。
      // 它要么是没权限（客户），要么是 CSRF 头出了问题。
      setSubmitError(err instanceof ApiError ? err.detail : '创建失败，请稍后重试')
      setBusy(false)
    }
  }

  if (loadError) {
    return (
      <Fault
        status={loadError instanceof ApiError ? loadError.status : 0}
        message={loadError instanceof ApiError ? loadError.detail : '加载失败'}
      />
    )
  }

  if (brands === null || platforms === null) {
    return (
      <Plate title="新建任务">
        <div style={{ display: 'grid', gap: 8 }}>
          <Pending height={20} />
          <Pending height={20} />
        </div>
      </Plate>
    )
  }

  const runnable = platforms.filter((p) => p.available)

  return (
    <form onSubmit={onSubmit}>
      <Plate title="新建任务" subtitle="任务盯一个品牌；每次执行会冻结当时的提问集与竞品集">
        <div style={{ display: 'grid', gap: 16, maxWidth: 520 }}>
          <label style={{ display: 'grid', gap: 6 }}>
            <span className={kit.fieldLabel}>品牌</span>
            <select
              className={kit.input}
              value={brandId}
              onChange={(e) => setBrandId(e.target.value === '' ? '' : Number(e.target.value))}
              disabled={busy}
              required
            >
              <option value="">请选择</option>
              {brands.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name}
                  {b.industry ? `（${b.industry}）` : ''}
                </option>
              ))}
            </select>
          </label>

          <label style={{ display: 'grid', gap: 6 }}>
            <span className={kit.fieldLabel}>任务名</span>
            <input
              className={kit.input}
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="例：安踏周度监测"
              maxLength={120}
              disabled={busy}
              required
            />
          </label>

          <div style={{ display: 'grid', gap: 6 }}>
            <span className={kit.fieldLabel}>平台</span>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {platforms.map((p) => (
                <button
                  key={p.code}
                  type="button"
                  className={`${kit.chip} ${picked.includes(p.code) ? kit.chipOn : ''}`}
                  onClick={() => togglePlatform(p.code)}
                  // 建完就跑不了的平台不给选 —— 否则用户看到的是「抓取失败」，
                  // 而真相是「这个平台没接」，两者排查方向完全不同。
                  disabled={!p.available || busy}
                  title={p.available ? undefined : (p.note ?? '该平台尚未接入')}
                >
                  {p.label}
                  {p.available ? '' : ' · 未接入'}
                </button>
              ))}
            </div>
            {runnable.length === 0 ? (
              <span style={{ color: 'var(--down)', fontSize: 'var(--fs-label)' }}>
                当前没有可用平台，建了任务也跑不起来。
              </span>
            ) : null}
          </div>

          <label style={{ display: 'grid', gap: 6, maxWidth: 200 }}>
            <span className={kit.fieldLabel}>每条提问采样次数</span>
            <input
              className={kit.input}
              type="number"
              min={1}
              max={20}
              value={samples}
              onChange={(e) => setSamples(Number(e.target.value))}
              disabled={busy}
              required
            />
          </label>

          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <Button type="submit" primary>
              {busy ? '创建中…' : '创建任务'}
            </Button>
            <Button onClick={() => router.back()}>取消</Button>
            {crawlMode === 'fake' ? (
              <Mark tone="warn">当前 crawl_mode=fake，产出的是假数据</Mark>
            ) : null}
          </div>

          {submitError ? (
            <p role="alert" style={{ color: 'var(--down)', fontSize: 'var(--fs-label)' }}>
              {submitError}
            </p>
          ) : null}
        </div>
      </Plate>

      <Aside>
        建任务<strong>不会</strong>立刻开始抓取。要跑得进任务详情点「立即运行」——
        那一步才会真的建 job、消耗额度。
      </Aside>
    </form>
  )
}
