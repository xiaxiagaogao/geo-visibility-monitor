'use client'

import { useRouter } from 'next/navigation'
import { useCallback, useEffect, useMemo, useState } from 'react'

import { HitMatrix, type MatrixColumn } from '@/components/charts/HitMatrix'
import { EmphasisBars } from '@/components/charts/EmphasisBars'
import { GapList } from '@/components/runs/GapList'
import { RunNowButton } from '@/components/runs/RunNowButton'
import { RunSwitcher } from '@/components/runs/RunSwitcher'
import runs from '@/components/runs/runs.module.css'
import {
  Badge,
  Button,
  EmptyState,
  ErrorState,
  KpiCount,
  KpiDegraded,
  KpiGrid,
  KpiRate,
  Panel,
  PanelNote,
  Skeleton,
  Tabs,
  ui,
} from '@/components/ui'
import { canWrite } from '@/lib/api/auth'
import { brandNameMap, listBrands } from '@/lib/api/brands'
import { ApiError } from '@/lib/api/client'
import { fetchRunCounts } from '@/lib/api/counts'
import { getRun, getTask, listRuns, startRun } from '@/lib/api/tasks'
import { useAuth } from '@/lib/auth-context'
import { findGaps } from '@/lib/l3/gaps'
import { buildMatrix, gapInputsFromMatrix } from '@/lib/l3/matrix'
import { runStatusLabel, runStatusTone } from '@/lib/l3/run-status'
import type { BarDatum, CountsResponse, Run, RunDetail, Task } from '@/lib/types'

import { SamplesPanel } from './SamplesPanel'
import { TaskEditPanel } from './TaskEditPanel'

/**
 * 任务详情（A6）。版式见 `apps/web/README.md` §2.3。
 *
 * `runId` 不传就落到最新一次运行；传了就钉在那一次。
 * **切 run 是换路由，不是换查询参数** —— 运营要把某一次运行的链接发给客户。
 *
 * 取数四路：`/v1/tasks/{id}` · `/{id}/runs` · `/v1/runs/{runId}` ·
 * `/v1/counts` 两次（`group_by=none` 出 KPI，`group_by=prompt` 出条形图 /
 * 缺口清单 / 矩阵）。**两次 counts 都带 `run_id`**，这由 `fetchRunCounts`
 * 的必填参数在类型层面保证。
 */
export function TaskDetailView({ taskId, runId }: { taskId: number; runId?: number }) {
  const router = useRouter()
  const { me } = useAuth()

  const [task, setTask] = useState<Task | null>(null)
  const [runList, setRunList] = useState<Run[] | null>(null)
  const [brands, setBrands] = useState<Map<number, string>>(new Map())
  const [error, setError] = useState<Error | null>(null)
  // 发起运行后要连任务、run 列表一起重取，否则切换器里没有新那一条
  const [reloadKey, setReloadKey] = useState(0)

  const reload = useCallback(() => setReloadKey((k) => k + 1), [])
  const [editing, setEditing] = useState(false)

  // 这个任务有没有一次运行还没跑完。轮询只在这时候开。
  const inFlight = (runList ?? []).some(
    (r) => r.status === 'pending' || r.status === 'running',
  )

  // **跑着的时候自动刷新（P2-03）。**
  //
  // 之前只能手点「刷新」——刚发起完盯着一个 pending 页面反复点，
  // 是这个页面最明显的一个窟窿。
  //
  // 三条约束：
  //   · **只在有 run 没跑完时开。** 跑完就停，不做无意义的轮询。
  //   · **页面不可见时不轮询**（切走的标签页、锁屏）。否则一个开着不管的
  //     标签页会整夜按秒打接口，而没有任何人在看。
  //   · 间隔 6 秒 —— 抓取本身以十秒计，再快只是徒增负载。
  useEffect(() => {
    if (!inFlight) return
    const tick = () => {
      if (typeof document !== 'undefined' && document.visibilityState !== 'visible') return
      reload()
    }
    const timer = setInterval(tick, 6000)
    return () => clearInterval(timer)
  }, [inFlight, reload])

  useEffect(() => {
    let alive = true
    setError(null)
    setTask(null)
    setRunList(null)
    Promise.all([getTask(taskId), listRuns(taskId), listBrands()])
      .then(([t, r, b]) => {
        if (!alive) return
        setTask(t)
        setRunList(r.items)
        setBrands(brandNameMap(b.items))
      })
      .catch((e: unknown) => {
        if (alive) setError(e instanceof Error ? e : new Error(String(e)))
      })
    return () => {
      alive = false
    }
  }, [taskId, reloadKey])

  // 没指定就落到最新。task.latest_run_id 已经在列表响应里，不必再算一遍
  const activeRunId = runId ?? task?.latest_run_id ?? runList?.[0]?.id ?? null

  // URL 里的 runId 不属于这个任务时要当场拦下。
  //
  // 后端拦得住一半：`/v1/counts` 会校验 run 与 brand 匹配（404）。但两个任务
  // 盯同一个品牌时那道校验是过的 —— 于是 task 34 的页头下面会画着 task 40
  // 那次运行的数，而切换器里根本没有这一项，select 显示空白。
  const runIdIsForeign =
    runId !== undefined && runList !== null && !runList.some((r) => r.id === runId)

  if (error) {
    return (
      <ErrorState
        status={error instanceof ApiError ? error.status : 0}
        message={
          // 404 同时意味着「不存在」和「不属于你」，后端刻意不区分（防枚举）。
          // 所以文案只能说「没有这条」，不能说「无权访问」。
          error instanceof ApiError && error.status === 404
            ? '没有这个任务，或它不在你的可见范围内'
            : error instanceof ApiError
              ? error.detail
              : '加载失败'
        }
        onRetry={reload}
      />
    )
  }

  if (task === null || runList === null) {
    return (
      <div style={{ display: 'grid', gap: 12 }}>
        <Skeleton height={28} width="40%" />
        <Skeleton height={92} />
      </div>
    )
  }

  return (
    <div className={runs.panelStack}>
      <TaskHeader
        task={task}
        brandName={brands.get(task.brand_id) ?? `#${task.brand_id}`}
        runList={runList}
        activeRunId={activeRunId}
        canRun={canWrite(me)}
        onEdit={() => setEditing((v) => !v)}
        editing={editing}
        onSwitch={(id) => router.push(`/tasks/${taskId}/runs/${id}`)}
        onStarted={(run) => {
          reload()
          router.push(`/tasks/${taskId}/runs/${run.id}`)
        }}
        onRefresh={reload}
      />

      {editing ? (
        <TaskEditPanel
          task={task}
          onSaved={() => {
            setEditing(false)
            reload()
          }}
          onCancel={() => setEditing(false)}
        />
      ) : null}

      {runIdIsForeign ? (
        <Panel>
          <EmptyState>
            <strong style={{ color: 'var(--text-secondary)' }}>
              这次运行不属于这个任务
            </strong>
            <span>
              链接里的 run #{runId} 不在「{task.name}」的运行历史里。
              用上面的切换器选一次，或回到{' '}
              <a className={ui.rowLink} href={`/tasks/${taskId}`}>
                任务详情
              </a>
              。
            </span>
          </EmptyState>
        </Panel>
      ) : activeRunId === null ? (
        <Panel>
          <EmptyState>
            <strong style={{ color: 'var(--text-secondary)' }}>这个任务还没运行过</strong>
            <span>
              {canWrite(me)
                ? '点右上角「立即运行」发起第一次检测 —— 那一步会冻结当前的提问集与竞品集。'
                : '还没有检测记录，请联系运营发起一次运行。'}
            </span>
          </EmptyState>
        </Panel>
      ) : (
        <RunReport
          key={activeRunId}
          taskId={taskId}
          brandId={task.brand_id}
          runId={activeRunId}
          refreshKey={reloadKey}
        />
      )}
    </div>
  )
}

/* ══════ 任务头 ══════ */

function TaskHeader({
  task,
  brandName,
  runList,
  activeRunId,
  canRun,
  onEdit,
  editing,
  onSwitch,
  onStarted,
  onRefresh,
}: {
  task: Task
  brandName: string
  runList: Run[]
  activeRunId: number | null
  canRun: boolean
  onEdit: () => void
  editing: boolean
  onSwitch: (runId: number) => void
  onStarted: (run: Run) => void
  onRefresh: () => void
}) {
  const [armed, setArmed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [startError, setStartError] = useState<string | null>(null)

  const active = runList.find((r) => r.id === activeRunId)

  // 「还在跑」的提示说的是**你正在看的**这一次
  const viewingInFlight = active?.status === 'pending' || active?.status === 'running'

  // 但按不按得下「立即运行」，看的是**这个任务有没有任何一次在跑**。
  // 拿正在看的那一次判断会漏：你翻回上个月一次 success 的 run，
  // 按钮就又亮了，于是同一批提问被两个 run 同时抓 ——
  // 两份互相看不见的数据，谁也说不清哪份是准的。
  const taskInFlight = runList.some((r) => r.status === 'pending' || r.status === 'running')

  // 停用的任务发起运行会被后端拒（400）。前端先拦，并把理由说出来 ——
  // 给一个点了必然失败的按钮比没有更糟。
  const inactive = !task.is_active

  async function confirmStart() {
    setBusy(true)
    setStartError(null)
    try {
      const run = await startRun(task.id)
      setArmed(false)
      onStarted(run)
    } catch (e) {
      // 403 **不跳登录页** —— 用户是登着的，跳了会陷入死循环。
      // 它要么是客户没写权限，要么是 CSRF 头出了问题。
      setStartError(e instanceof ApiError ? e.detail : '发起失败，请稍后重试')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <div className={runs.taskHead}>
        <div>
          <h1 className={runs.taskTitle}>
            {task.name}
            <Badge tone="accent">{brandName}</Badge>
            {task.is_active ? null : <Badge>已停用</Badge>}
          </h1>
          <div className={runs.taskMeta}>
            <span>{(active?.platforms.length ? active.platforms : task.platforms).join(' · ') || '未选平台'}</span>
            <span>·</span>
            <span>每条提问采样 {task.samples} 次</span>
            {runList.length ? (
              <>
                <span>·</span>
                <span>共 {runList.length} 次运行</span>
              </>
            ) : null}
          </div>
        </div>

        <div className={runs.taskActions}>
          {/* 只在 activeRunId 真在列表里时才画 —— 一个 value 不在 options
              里的 select 会渲染成空白框，看起来像坏了 */}
          {active ? (
            <RunSwitcher runs={runList} currentRunId={active.id} onChange={onSwitch} />
          ) : null}
          <Button onClick={onRefresh}>刷新</Button>
          {canRun ? (
            <Button onClick={onEdit}>{editing ? '收起编辑' : '编辑'}</Button>
          ) : null}
          {/* 按钮灰掉必须给理由。一个没解释的灰按钮，用户只会当它坏了 */}
          {canRun && inactive ? (
            <span style={{ fontSize: 'var(--fs-xs)', color: 'var(--text-tertiary)' }}>
              任务已停用
            </span>
          ) : canRun && taskInFlight ? (
            <span style={{ fontSize: 'var(--fs-xs)', color: 'var(--text-tertiary)' }}>
              有一次运行还没跑完
            </span>
          ) : null}
          {/* 按角色隐藏只是体验，不是安全边界 —— 服务端的 require_write 才是 */}
          {canRun ? (
            <RunNowButton
              armed={armed}
              onArm={() => setArmed(true)}
              onCancel={() => setArmed(false)}
              onConfirm={confirmStart}
              busy={busy}
              lastJobCount={runList[0]?.n_jobs}
              disabled={taskInFlight || inactive}
            />
          ) : null}
        </div>
      </div>

      {viewingInFlight ? (
        <PanelNote>
          这次运行还在进行中（{runStatusLabel(active?.status ?? null)}），
          此时的数字是<strong>跑到一半</strong>的数字，分母还会涨。
          页面每 6 秒自动刷新一次（切走标签页时暂停）。
        </PanelNote>
      ) : null}

      {startError ? (
        <p role="alert" style={{ color: 'var(--danger)', fontSize: 'var(--fs-xs)' }}>
          {startError}
        </p>
      ) : null}
    </div>
  )
}

/* ══════ 某一次运行的全部内容 ══════ */

function RunReport({
  taskId,
  brandId,
  runId,
  refreshKey,
}: {
  /** 只用来拼证据页链接；这一页的每个数字都来自 runId */
  taskId: number
  brandId: number
  runId: number
  /** 变化即重取 —— 让上层的手动刷新与自动轮询也能带动报告体里的数字 */
  refreshKey: number
}) {
  const [run, setRun] = useState<RunDetail | null>(null)
  const [overall, setOverall] = useState<CountsResponse | null>(null)
  const [byPrompt, setByPrompt] = useState<CountsResponse | null>(null)
  const [error, setError] = useState<Error | null>(null)
  const [tab, setTab] = useState('matrix')
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let alive = true
    setError(null)
    setRun(null)
    setOverall(null)
    setByPrompt(null)
    Promise.all([
      getRun(runId),
      fetchRunCounts({ brandId, runId }),
      fetchRunCounts({ brandId, runId, groupBy: 'prompt' }),
    ])
      .then(([r, o, p]) => {
        if (!alive) return
        setRun(r)
        setOverall(o)
        setByPrompt(p)
      })
      .catch((e: unknown) => {
        if (alive) setError(e instanceof Error ? e : new Error(String(e)))
      })
    return () => {
      alive = false
    }
  }, [brandId, runId, attempt, refreshKey])

  const rows = useMemo(() => {
    if (!run || !byPrompt) return []
    return buildMatrix({
      ownBrandId: brandId,
      prompts: run.prompts,
      competitors: run.competitors,
      series: byPrompt.series,
    })
  }, [run, byPrompt, brandId])

  const gaps = useMemo(() => findGaps(gapInputsFromMatrix(rows)), [rows])

  if (error) {
    return (
      <ErrorState
        status={error instanceof ApiError ? error.status : 0}
        message={error instanceof ApiError ? error.detail : '加载失败'}
        onRetry={() => setAttempt((a) => a + 1)}
      />
    )
  }

  if (!run || !overall || !byPrompt) {
    return (
      <div style={{ display: 'grid', gap: 12 }}>
        <Skeleton height={96} />
        <Skeleton height={200} />
      </div>
    )
  }

  const den = overall.denominator
  const brand = overall.brand
  const unusable = den.n_total_responses - den.n_valid

  if (run.status === 'empty') {
    return (
      <Panel title="这次运行没有产生任何采样">
        <EmptyState>
          <strong style={{ color: 'var(--text-secondary)' }}>一条 job 都没建出来</strong>
          <span>
            这是<strong>配置问题</strong>，不是采集失败：发起时这个品牌没有启用中的提问词，
            或者任务的平台是空的。去品牌页补提问词后再运行一次。
          </span>
        </EmptyState>
      </Panel>
    )
  }

  if (den.n_valid === 0) {
    return (
      <Panel
        title="这次运行还没有有效样本"
        right={<Badge tone={runStatusTone(run.status)}>{runStatusLabel(run.status)}</Badge>}
      >
        <EmptyState>
          <strong style={{ color: 'var(--text-secondary)' }}>
            {run.n_jobs} 个采样里没有一条可用
          </strong>
          <span>
            {run.status === 'pending' || run.status === 'running'
              ? '还在跑，跑完再看。'
              : '全部落在 empty / too_short / error 上 —— 分母是 0，任何比率都算不出来，所以这里不画 0%。'}
          </span>
        </EmptyState>
      </Panel>
    )
  }

  // 逐提问条形图按提及率降序：总提及率是各条平均出来的，可能由「几条满分 +
  // 几条挂零」构成，而这个结构才是结论。按 prompt_id 排会把它打散
  // （series 的 key 还是字符串序，"10" 排在 "9" 前面）。
  const bars: BarDatum[] = rows
    .map((r) => ({ key: r.promptId, label: r.promptText, m: r.ownM, n: r.n, own: true }))
    .sort((a, b) => {
      const ra = a.n > 0 ? a.m / a.n : -1
      const rb = b.n > 0 ? b.m / b.n : -1
      return rb - ra || Number(a.key) - Number(b.key)
    })

  const columns: MatrixColumn[] = [
    { brandId, label: '本品', own: true },
    ...run.competitors.map((c) => ({ brandId: c.competitor_brand_id, label: c.brand_name })),
  ]

  const promptText = new Map(run.prompts.map((p) => [p.prompt_id, p.prompt_text]))
  const brandNames = new Map(run.competitors.map((c) => [c.competitor_brand_id, c.brand_name]))

  return (
    <div className={runs.panelStack}>
      {run.status === 'partial' ? (
        <PanelNote>
          <strong>部分成功。</strong>
          {run.n_jobs} 个采样里只有 {den.n_total_responses} 条回来了，
          分母比预期少一截 —— 下面所有比率都会偏高，别拿它和一次完整运行直接比。
        </PanelNote>
      ) : null}

      {run.note ? <PanelNote>{run.note}</PanelNote> : null}

      <KpiGrid>
        <KpiCount
          label="有效样本"
          info="分母口径：answer_status = ok"
          value={den.n_valid}
          note={
            unusable > 0
              ? `共 ${den.n_total_responses} 条响应，${unusable} 条不可用`
              : `共 ${den.n_total_responses} 条响应，全部可用`
          }
          alert={unusable > 0}
        />

        <KpiRate
          label="提及率"
          info="本品被提及的样本数 / 有效样本数"
          m={brand.m_mentioned}
          n={den.n_valid}
          alert={brand.m_mentioned === 0}
        />

        {/* m_first 取不到时走降级态，**不许当 0** ——
            「一次都没排第一」和「这个数还取不到」是完全不同的结论。 */}
        {brand.m_first === undefined ? (
          <KpiDegraded
            label="首位提及率"
            info="出场顺位为 1 的样本数 / 被提及的样本数"
            reason="暂无排名数据"
            note="counts 未返回 m_first，后端上线该字段后自动恢复"
          />
        ) : (
          <KpiRate
            label="首位提及率"
            info="出场顺位为 1 的样本数 / 被提及的样本数。是位置事实，不是「AI 首推」"
            m={brand.m_first}
            n={brand.m_mentioned}
          />
        )}

        <KpiCount
          label="覆盖缺口"
          info="本品缺席或明显落后、且竞品在场的提问数"
          value={gaps.length}
          note={`共 ${rows.length} 条提问`}
          alert={gaps.length > 0}
        />
      </KpiGrid>

      <Panel
        title="逐提问提及率"
        subtitle="上面那个总提及率是这些条平均出来的 —— 它可能由几条满分加几条挂零构成"
      >
        <EmphasisBars data={bars} />
      </Panel>

      <Panel
        title="覆盖缺口"
        subtitle="本品缺席或明显落后、而竞品在场的提问。右侧数字是失分量：竞品合计比本品多拿的提及次数"
      >
        <GapList
          gaps={gaps}
          promptText={promptText}
          brandName={brandNames}
          totalPrompts={rows.length}
        />
      </Panel>

      <Panel>
        <Tabs
          items={[
            { id: 'matrix', label: '命中矩阵', count: rows.length },
            // 计数用**总响应数**而不是 n_valid：样本表把不可用的那些也列出来
            // （标着「不进分母」），tab 上的数字必须和表里的行数对得上
            { id: 'samples', label: '样本列表', count: den.n_total_responses },
          ]}
          active={tab}
          onChange={setTab}
        />
        {tab === 'matrix' ? (
          <HitMatrix rows={rows} columns={columns} />
        ) : (
          <SamplesPanel runId={runId} ownBrandId={brandId} taskId={taskId} />
        )}
      </Panel>
    </div>
  )
}
