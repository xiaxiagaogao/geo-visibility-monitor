'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useEffect, useState, type FormEvent } from 'react'

import { Mark, Button, Fault, PageHead, Plate, Aside, Pending, kit } from '@/components/kit'
import { listBrands } from '@/lib/api/brands'
import { ApiError } from '@/lib/api/client'
import { fetchPlatforms } from '@/lib/api/config'
import { listPrompts } from '@/lib/api/prompts'
import { createTask, listTasks } from '@/lib/api/tasks'
import { classifyBrands } from '@/lib/l3/brand-roles'
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
  const [reloadKey, setReloadKey] = useState(0)

  const [brandId, setBrandId] = useState<number | ''>('')
  const [name, setName] = useState('')
  const [picked, setPicked] = useState<string[]>([])
  const [samples, setSamples] = useState(3)
  const [busy, setBusy] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  /** null = 还没选品牌 / 数不出来；'loading' = 在数 */
  const [promptCount, setPromptCount] = useState<number | 'loading' | null>(null)

  useEffect(() => {
    // **下拉里只放监测对象。**
    //
    // `/v1/brands` 返回全部 17 个，其中 15 个是只作为竞品参照存在的。
    // 不筛的话可以给「耐克」建一个任务 —— 那几乎肯定是误操作，而且建完
    // 才发现要删（删任务是级联的）。判据和品牌列表用的是同一个 L3 函数。
    Promise.all([listBrands(), listTasks(), fetchPlatforms()])
      .then(([b, t, p]) => {
        const roster = classifyBrands(b.items, t.items)
        const pickable = roster.monitored.map((m) => m.brand)
        setBrands(pickable)
        setPlatforms(p.items)
        setCrawlMode(p.crawl_mode)
        // 只有一个品牌时直接选上，省一次点击
        if (pickable.length === 1) setBrandId(pickable[0].id)
      })
      .catch((e: unknown) => setLoadError(e instanceof Error ? e : new Error(String(e))))
  }, [reloadKey])

  /**
   * 选中品牌后去数它有几条**启用中**的提问词。
   *
   * 提问集住在品牌详情里，而它是任务的输入 —— 这个先后顺序此前没有任何地方
   * 说明。一个提问集为空的品牌建出来的任务，跑起来什么都采不到，
   * 而用户要到「立即运行」之后才发现。
   */
  useEffect(() => {
    if (brandId === '') {
      setPromptCount(null)
      return
    }
    let alive = true
    setPromptCount('loading')
    listPrompts({ brandId, activeOnly: true })
      .then((r) => {
        if (alive) setPromptCount(r.items.length)
      })
      .catch(() => {
        // 数不出来不该挡住建任务 —— 它只是个提醒，不是校验
        if (alive) setPromptCount(null)
      })
    return () => {
      alive = false
    }
  }, [brandId])

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
        /* 没有重试的话，这一页初次加载失败就只能离开再回来 —— 而用户
           多半不知道那是唯一出路，只会以为「新建任务坏了」。 */
        onRetry={() => setReloadKey((k) => k + 1)}
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
      {/* 这一页此前**整页没有 h1** —— 标题塞在面板的 h2 里，和改版前的
          /brands、/users 是同一个毛病，当时漏了这两个 /new。 */}
      <PageHead
        title="新建任务"
        lede="任务盯一个品牌；每次执行会冻结当时的提问集与竞品集。"
        back={{ href: '/tasks', label: '检测任务' }}
      />
      <Plate>
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
            {/* 提问集是任务的输入，但它住在**品牌**详情里 —— 这个先后顺序
                此前没有任何地方说明。提问集为空的品牌建出来的任务跑起来
                什么都采不到，而用户要到「立即运行」之后才发现。 */}
            {promptCount === 'loading' ? (
              <span className={kit.fieldHint}>正在数提问集…</span>
            ) : promptCount === 0 ? (
              <span className={kit.fieldHintAlert}>
                这个品牌<strong>还没有启用中的提问词</strong> —— 任务建出来能跑，
                但一条都采不到。先去{' '}
                <Link href={`/brands/${brandId}`} className={kit.rowLink}>
                  它的品牌页
                </Link>{' '}
                配提问集。
              </span>
            ) : typeof promptCount === 'number' ? (
              <span className={kit.fieldHint}>
                这个品牌有 <strong>{promptCount}</strong> 条启用中的提问词，
                发起运行时会连同竞品集一起冻结。{' '}
                <Link href={`/brands/${brandId}`} className={kit.rowLink}>
                  去改
                </Link>
              </span>
            ) : null}
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
