'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useCallback, useEffect, useMemo, useState } from 'react'

import {
  Aside,
  Blank,
  Button,
  Fault,
  Instrument,
  Mark,
  markTone,
  Pending,
  Plate,
  Notation,
  Notices,
  PageHead,
  type Notice,
  ReadoutBlank,
  ReadoutCount,
  ReadoutRate,
  Table,
  kit,
} from '@/components/kit'
import { HitGrid, type GridColumn } from '@/components/kit/HitGrid'
import { TraceBars } from '@/components/kit/TraceBars'
import { TrendArea } from '@/components/kit/TrendArea'
import { ExportGapsButton } from '@/components/runs/ExportGapsButton'
import { GapList } from '@/components/runs/GapList'
import { RunNowButton } from '@/components/runs/RunNowButton'
import { RunSwitcher } from '@/components/runs/RunSwitcher'
import runs from '@/components/runs/runs.module.css'
import { canWrite } from '@/lib/api/auth'
import { brandNameMap, listBrands } from '@/lib/api/brands'
import { ApiError } from '@/lib/api/client'
import { fetchPlatforms } from '@/lib/api/config'
import { fetchRunCounts } from '@/lib/api/counts'
import { getRun, getTask, listRuns, startRun } from '@/lib/api/tasks'
import { useAuth } from '@/lib/auth-context'
import { gapCsvFileName, gapCsvRows } from '@/lib/l3/gap-export'
import { findGaps } from '@/lib/l3/gaps'
import { buildMatrix, gapInputsFromMatrix } from '@/lib/l3/matrix'
import { denominatorParts, platformBars, platformSlices } from '@/lib/l3/platforms'
import { formatFraction, formatRate } from '@/lib/l3/rates'
import { runStatusLabel, runStatusTone } from '@/lib/l3/run-status'
import { buildTrend, incompleteCount, type TrendPoint } from '@/lib/l3/trend'
import type {
  BarDatum,
  CountsResponse,
  PlatformOption,
  Run,
  RunDetail,
  Task,
} from '@/lib/types'

import { SamplesPanel } from './SamplesPanel'
import { TaskEditPanel } from './TaskEditPanel'

/**
 * 任务详情（A6）。
 *
 * 版式在改版中重排过一次，顺序是有理由的：
 *
 *   页头 → **历次运行（全部 run 的时间线）** → 仪器面板（这一次的读数）→ 逐提问 → 缺口 → 矩阵/样本
 *
 * 时间线排在读数之前，是因为「这一次是 66.7%」这句话单独说出来没有意义 ——
 * 得先知道它在这条线上处于什么位置、以及中间有没有换过口径。
 *
 * `runId` 不传就落到最新一次运行；传了就钉在那一次。
 * **切 run 是换路由，不是换查询参数** —— 运营要把某一次运行的链接发给客户。
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
      <Fault
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
      <div className={runs.stack}>
        <Pending height={34} width="38%" />
        <Pending height={168} />
        <Pending height={128} />
      </div>
    )
  }

  return (
    <div className={runs.stack}>
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

      {/* 历次运行：整个任务的时间线。它在读数之前 —— 一个孤零零的「66.7%」
          说不清自己处在什么位置。 */}
      <TrendPlate
        taskId={taskId}
        brandId={task.brand_id}
        runList={runList}
        activeRunId={activeRunId}
        refreshKey={reloadKey}
      />

      {runIdIsForeign ? (
        <Plate>
          <Blank lead="这次运行不属于这个任务">
            链接里的 run #{runId} 不在「{task.name}」的运行历史里。
            用上面的图或切换器选一次。
          </Blank>
        </Plate>
      ) : activeRunId === null ? (
        <Plate>
          <Blank lead="这个任务还没运行过">
            {canWrite(me)
              ? '点右上角「立即运行」发起第一次检测 —— 那一步会冻结当前的提问集与竞品集。'
              : '还没有检测记录，请联系运营发起一次运行。'}
          </Blank>
        </Plate>
      ) : (
        <RunReport
          key={activeRunId}
          taskId={taskId}
          brandId={task.brand_id}
          runId={activeRunId}
          refreshKey={reloadKey}
          taskName={task.name}
        />
      )}
    </div>
  )
}

/* ══════════════════════════════════════════════════════════════════
   页头
   ══════════════════════════════════════════════════════════════════ */

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
}) {
  const [armed, setArmed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState('')
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
      const run = await startRun(task.id, note)
      setArmed(false)
      setNote('')
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
      <PageHead
        title={
          <>
            {task.name}
            <Mark tone="own">{brandName}</Mark>
            {task.is_active ? null : <Mark>已停用</Mark>}
          </>
        }
        meta={
          <>
            <span>
              {(active?.platforms.length ? active.platforms : task.platforms).join(' · ') ||
                '未选平台'}
            </span>
            <span className={runs.metaSep}>·</span>
            <span>每条提问采样 {task.samples} 次</span>
            {runList.length ? (
              <>
                <span className={runs.metaSep}>·</span>
                <span>共 {runList.length} 次运行</span>
              </>
            ) : null}
          </>
        }
        action={
          <div className={runs.actions}>
          {/* 只在 activeRunId 真在列表里时才画 —— 一个 value 不在 options
              里的 select 会渲染成空白框，看起来像坏了 */}
          {active ? (
            <RunSwitcher runs={runList} currentRunId={active.id} onChange={onSwitch} />
          ) : null}
          {canRun ? (
            <Button onClick={onEdit}>{editing ? '收起编辑' : '编辑'}</Button>
          ) : null}
          {/* 按钮灰掉必须给理由。一个没解释的灰按钮，用户只会当它坏了 */}
          {canRun && inactive ? (
            <span className={runs.reason}>任务已停用</span>
          ) : canRun && taskInFlight ? (
            <span className={runs.reason}>有一次运行还没跑完</span>
          ) : null}
          {/* 按角色隐藏只是体验，不是安全边界 —— 服务端的 require_write 才是 */}
          {canRun ? (
            <RunNowButton
              armed={armed}
              onArm={() => setArmed(true)}
              onCancel={() => setArmed(false)}
              onConfirm={confirmStart}
              note={note}
              onNoteChange={setNote}
              busy={busy}
              lastJobCount={runList[0]?.n_jobs}
              disabled={taskInFlight || inactive}
            />
          ) : null}
          </div>
        }
      />

      {viewingInFlight ? (
        <div style={{ marginTop: 'var(--sp-4)' }}>
          <Aside tone="alert">
            这次运行还在进行中（{runStatusLabel(active?.status ?? null)}），
            此时的数字是<strong>跑到一半</strong>的数字，分母还会涨。
            页面每 6 秒自动刷新一次（切走标签页时暂停）。
          </Aside>
        </div>
      ) : null}

      {startError ? (
        <p role="alert" style={{ color: 'var(--down)', fontSize: 'var(--fs-sm)' }}>
          {startError}
        </p>
      ) : null}
    </div>
  )
}

/* ══════════════════════════════════════════════════════════════════
   历次运行
   ══════════════════════════════════════════════════════════════════ */

/** 最多画这么多次运行。再往前的记录在这个宽度上挤成一团，读不出东西。 */
const MAX_RUNS_ON_STRIP = 24

function TrendPlate({
  taskId,
  brandId,
  runList,
  activeRunId,
  refreshKey,
}: {
  taskId: number
  brandId: number
  runList: Run[]
  activeRunId: number | null
  refreshKey: number
}) {
  const router = useRouter()
  const [points, setPoints] = useState<TrendPoint[] | null>(null)

  const recent = useMemo(
    () =>
      [...runList]
        .sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at))
        .slice(0, MAX_RUNS_ON_STRIP),
    [runList],
  )

  useEffect(() => {
    if (recent.length === 0) {
      setPoints([])
      return
    }
    let alive = true
    setPoints(null)
    // **allSettled 而不是 all**：一次运行取不到 counts 不该让整条时间线消失。
    // 取不到的那次在 buildTrend 里直接不出现 —— 绝不在轴上补一个 0。
    Promise.allSettled(
      recent.map((r) =>
        fetchRunCounts({ brandId, runId: r.id }).then(
          (c) => [r.id, c] as [number, CountsResponse],
        ),
      ),
    ).then((results) => {
      if (!alive) return
      const map = new Map<number, CountsResponse>()
      for (const res of results) {
        if (res.status === 'fulfilled') map.set(res.value[0], res.value[1])
      }
      setPoints(buildTrend(recent, map))
    })
    return () => {
      alive = false
    }
  }, [brandId, recent, refreshKey])

  if (points === null) {
    return (
      <Plate title="历次运行">
        <Pending height={128} />
      </Plate>
    )
  }

  // 一次运行画不出记录 —— 一个点不是趋势，画出来是在暗示一条线
  if (points.length < 2) {
    return null
  }

  const partial = incompleteCount(points)
  const torn = points.filter((p) => p.breaks.includes('platforms')).length

  return (
    <Plate
      title="历次运行"
      subtitle={`${points.length} 次运行，本品提及率沿真实时间排开。点图上任意一次即可切过去。`}
      right={
        <span className={runs.reason}>
          {torn > 0 ? `${torn} 处断口` : '无断口'}
        </span>
      }
    >
      <TrendArea
        points={points}
        activeRunId={activeRunId}
        onPick={(id) => router.push(`/tasks/${taskId}/runs/${id}`)}
      />

      <Notation
        entries={[
          { swatch: 'var(--accent)', label: '本品提及率' },
          { swatch: 'whisker', label: '竞品区间 —— 每次运行的最低~最高' },
          { swatch: 'void', label: '空心方标 = 分母不完整' },
        ]}
        note="纵轴 0–100%"
      />

      {/* 图的表格孪生。
          规矩：**悬停卡不能是读到数值的唯一入口** —— 键盘用户够不着，
          触屏上要长按，读屏软件里那张 SVG 只有一句 aria-label。
          这张表是同一份数据的 WCAG 干净版本，顺带也是运营复制粘贴的入口。 */}
      <TrendTable points={points} activeRunId={activeRunId} taskId={taskId} />

      {/* 这两条一条都不能删 —— 它们是这个产品拒绝说好听话的地方。
          但四段说明曾把首屏 307px 占满、把读数全推到折叠线以下，
          所以改成默认一行、点开展全文（见 kit/Notices）。 */}
      <div style={{ marginTop: 'var(--sp-4)' }}>
        <Notices
          items={[
            ...(torn > 0
              ? [
                  {
                    label: `${torn} 处口径断点`,
                    tone: 'alert' as const,
                    body: (
                      <>
                        这条线上有 <strong>{torn}</strong> 处断口 ——
                        那几处<strong>平台集变过</strong>，前后两段的分母构成不同，
                        <strong>不能直接比</strong>。断口两侧的线是分开画的，不连过去。
                      </>
                    ),
                  },
                ]
              : []),
            {
              label: '断点判据的限度',
              body: (
                <>
                  断口只认<strong>平台集变化</strong>。提问集改过不会在这里显示 ——
                  那要逐次运行取快照比对（{points.length} 次运行就是 {points.length} 个额外请求）。
                  所以<strong>没有断口不等于口径没变过</strong>；带说明的那几次在轴下有一个小三角，
                  把鼠标放上去能看到当时写了什么。
                  {partial > 0 ? (
                    <>
                      {' '}另有 <strong>{partial}</strong> 次运行的分母不完整（空心方标），
                      它们的比率会偏高。
                    </>
                  ) : null}
                </>
              ),
            },
          ]}
        />
      </div>
    </Plate>
  )
}

/* ══════════════════════════════════════════════════════════════════
   历次运行的表格孪生
   ══════════════════════════════════════════════════════════════════ */

function TrendTable({
  points,
  activeRunId,
  taskId,
}: {
  points: TrendPoint[]
  activeRunId: number | null
  taskId: number
}) {
  return (
    <details className={runs.tableTwin}>
      <summary>看数值（{points.length} 次运行）</summary>
      <Table>
        <thead>
          <tr>
            <th>时间</th>
            <th>提及率</th>
            <th>本品 / 分母</th>
            <th>竞品最低~最高</th>
            <th>平台</th>
            <th>说明</th>
          </tr>
        </thead>
        <tbody>
          {points.map((p) => (
            <tr key={p.runId} aria-current={p.runId === activeRunId ? 'true' : undefined}>
              <td>
                <Link href={`/tasks/${taskId}/runs/${p.runId}`} className={kit.rowLink}>
                  {fmtWhen(p.at)}
                </Link>
              </td>
              {/* 比率和分母**永远同框** —— 这条在表格里也不松（README §3.1） */}
              <td className={kit.numeric}>{formatRate(p.r)}</td>
              <td className={kit.numeric}>{formatFraction(p.m, p.n)}</td>
              <td className={kit.numeric}>
                {p.competitorBand
                  ? `${formatRate(p.competitorBand.min)} ~ ${formatRate(p.competitorBand.max)}`
                  : '—'}
              </td>
              <td>{p.platforms.join(' · ') || '—'}</td>
              <td>
                {p.incomplete ? <Mark tone="warn">分母不完整</Mark> : null}
                {p.breaks.includes('platforms') ? <Mark tone="fault">口径断点</Mark> : null}
                {p.note ? <span className={runs.reason}>{p.note}</span> : null}
              </td>
            </tr>
          ))}
        </tbody>
      </Table>
    </details>
  )
}

function fmtWhen(iso: string): string {
  const d = new Date(iso)
  const z = (x: number) => String(x).padStart(2, '0')
  return `${d.getFullYear()}-${z(d.getMonth() + 1)}-${z(d.getDate())} ${z(d.getHours())}:${z(d.getMinutes())}`
}

/* ══════════════════════════════════════════════════════════════════
   某一次运行的全部内容
   ══════════════════════════════════════════════════════════════════ */

function RunReport({
  taskId,
  brandId,
  runId,
  refreshKey,
  taskName,
}: {
  /** 只用来拼证据页链接；这一页的每个数字都来自 runId */
  taskId: number
  brandId: number
  runId: number
  /** 只用来拼导出文件名 —— 上下文全靠文件名承载 */
  taskName: string
  /** 变化即重取 —— 让上层的手动刷新与自动轮询也能带动报告体里的数字 */
  refreshKey: number
}) {
  const [run, setRun] = useState<RunDetail | null>(null)
  const [overall, setOverall] = useState<CountsResponse | null>(null)
  const [byPrompt, setByPrompt] = useState<CountsResponse | null>(null)
  const [byPlatform, setByPlatform] = useState<CountsResponse | null>(null)
  const [platformOptions, setPlatformOptions] = useState<PlatformOption[]>([])
  /** 命中矩阵看哪个平台（P2-09）。`null` = 还没定/单平台，用 byPrompt 那份 */
  const [activePlatform, setActivePlatform] = useState<string | null>(null)
  const [byPromptOnePlatform, setByPromptOnePlatform] = useState<CountsResponse | null>(null)
  const [error, setError] = useState<Error | null>(null)
  const [tab, setTab] = useState('matrix')
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let alive = true
    setError(null)
    setRun(null)
    setOverall(null)
    setByPrompt(null)
    setByPlatform(null)
    setActivePlatform(null)
    setByPromptOnePlatform(null)
    Promise.all([
      getRun(runId),
      fetchRunCounts({ brandId, runId }),
      fetchRunCounts({ brandId, runId, groupBy: 'prompt' }),
      // 分平台面板的数据源：**一次请求**（PHASE2 §4.0 第 2 条）
      fetchRunCounts({ brandId, runId, groupBy: 'platform' }),
      // 平台标签**不许硬编码**（API.md §5）—— 接下一个平台时前端零改动
      fetchPlatforms(),
    ])
      .then(([r, o, p, pf, cfg]) => {
        if (!alive) return
        setRun(r)
        setOverall(o)
        setByPrompt(p)
        setByPlatform(pf)
        setPlatformOptions(cfg.items)
      })
      .catch((e: unknown) => {
        if (alive) setError(e instanceof Error ? e : new Error(String(e)))
      })
    return () => {
      alive = false
    }
  }, [brandId, runId, attempt, refreshKey])

  const slices = useMemo(
    () => (byPlatform ? platformSlices(byPlatform, platformOptions) : []),
    [byPlatform, platformOptions],
  )
  const multiPlatform = slices.length > 1

  // 多平台时矩阵默认落在第一个平台上（§4.0 第 3 条）
  useEffect(() => {
    if (multiPlatform && activePlatform === null) setActivePlatform(slices[0].code)
  }, [multiPlatform, activePlatform, slices])

  // **矩阵专用的那次取数** —— 只有它带 platform。
  // 缺口清单与逐提问条形图继续用不带 platform 的 byPrompt：
  // §4.0 第 4 条要求缺口跨平台合计（补内容的动作是平台无关的，
  // 而且合计之后样本翻倍、判级更稳）。
  useEffect(() => {
    if (!activePlatform) return
    let alive = true
    setByPromptOnePlatform(null)
    fetchRunCounts({ brandId, runId, groupBy: 'prompt', platform: activePlatform })
      .then((c) => {
        if (alive) setByPromptOnePlatform(c)
      })
      .catch((e: unknown) => {
        if (alive) setError(e instanceof Error ? e : new Error(String(e)))
      })
    return () => {
      alive = false
    }
  }, [brandId, runId, activePlatform, attempt, refreshKey])

  /** 缺口清单与条形图的口径：**跨平台合计**，不随矩阵的平台按钮变。 */
  const rows = useMemo(() => {
    if (!run || !byPrompt) return []
    return buildMatrix({
      ownBrandId: brandId,
      prompts: run.prompts,
      competitors: run.competitors,
      series: byPrompt.series,
    })
  }, [run, byPrompt, brandId])

  /** 矩阵的口径：**单平台**。单平台 run 时就是 rows 本身，不额外取数。 */
  const matrixRows = useMemo(() => {
    if (!run) return []
    if (!multiPlatform) return rows
    if (!byPromptOnePlatform) return []
    return buildMatrix({
      ownBrandId: brandId,
      prompts: run.prompts,
      competitors: run.competitors,
      series: byPromptOnePlatform.series,
    })
  }, [run, rows, multiPlatform, byPromptOnePlatform, brandId])

  const gaps = useMemo(() => findGaps(gapInputsFromMatrix(rows)), [rows])

  if (error) {
    return (
      <Fault
        status={error instanceof ApiError ? error.status : 0}
        message={error instanceof ApiError ? error.detail : '加载失败'}
        onRetry={() => setAttempt((a) => a + 1)}
      />
    )
  }

  if (!run || !overall || !byPrompt) {
    return (
      <div className={runs.stack}>
        <Pending height={150} />
        <Pending height={220} />
      </div>
    )
  }

  const den = overall.denominator
  const brand = overall.brand
  const unusable = den.n_total_responses - den.n_valid
  const live = run.status === 'pending' || run.status === 'running'
  // 单平台时 denominatorParts 返回空数组 → composition 为空 → 那一行不出现
  const composition = denominatorParts(slices)
    .map((x) => `${x.label} ${x.n}`)
    .join(' + ')

  if (run.status === 'empty') {
    return (
      <Plate title="这次运行没有产生任何采样">
        <Blank lead="一条 job 都没建出来">
          这是<strong>配置问题</strong>，不是采集失败：发起时这个品牌没有启用中的提问词，
          或者任务的平台是空的。去品牌页补提问词后再运行一次。
        </Blank>
      </Plate>
    )
  }

  if (den.n_valid === 0) {
    return (
      <Plate
        title="这次运行还没有有效样本"
        right={
          <Mark tone={markTone(runStatusTone(run.status))} dot>
            {runStatusLabel(run.status)}
          </Mark>
        }
      >
        <Blank lead={`${run.n_jobs} 个采样里没有一条可用`}>
          {run.status === 'pending' || run.status === 'running'
            ? '还在跑，跑完再看。'
            : '全部落在 empty / too_short / error 上 —— 分母是 0，任何比率都算不出来，所以这里不画 0%。'}
        </Blank>
      </Plate>
    )
  }

  // 逐提问按提及率降序：总提及率是各条平均出来的，可能由「几条满分 +
  // 几条挂零」构成，而这个结构才是结论。按 prompt_id 排会把它打散
  // （series 的 key 还是字符串序，"10" 排在 "9" 前面）。
  const bars: BarDatum[] = rows
    .map((r) => ({ key: r.promptId, label: r.promptText, m: r.ownM, n: r.n, own: true }))
    .sort((a, b) => {
      const ra = a.n > 0 ? a.m / a.n : -1
      const rb = b.n > 0 ? b.m / b.n : -1
      return rb - ra || Number(a.key) - Number(b.key)
    })

  const columns: GridColumn[] = [
    { brandId, label: '本品', own: true },
    ...run.competitors.map((c) => ({ brandId: c.competitor_brand_id, label: c.brand_name })),
  ]

  const promptText = new Map(run.prompts.map((p) => [p.prompt_id, p.prompt_text]))
  const brandNames = new Map(run.competitors.map((c) => [c.competitor_brand_id, c.brand_name]))

  return (
    <div className={runs.stack}>
      {/* 同上：默认一行，点开展全文。
          「部分成功」必须在读数**之前**出现 —— 它决定那几个比率可不可信。 */}
      <Notices
        items={[
          ...(run.status === 'partial'
            ? [
                {
                  label: '本次部分成功',
                  tone: 'alert' as const,
                  body: (
                    <>
                      <strong>部分成功。</strong>
                      {run.n_jobs} 个采样里只有 {den.n_total_responses} 条回来了，
                      分母比预期少一截 —— 下面所有比率都会偏高，别拿它和一次完整运行直接比。
                    </>
                  ),
                } as Notice,
              ]
            : []),
          ...(run.note ? [{ label: '带运行说明', body: run.note } as Notice] : []),
        ]}
      />

      {/* 一块面板，四个读数，中间用细线分隔 —— 不是四张一样大的卡片 */}
      <Instrument>
        <ReadoutCount
          label="有效样本"
          gloss="分母口径：answer_status = ok"
          value={den.n_valid}
          live={live}
          note={
            // **多平台时把分母的构成摊开**（PHASE2 §4.0 第 1 条）——
            // 单平台 `21/35` 够了，多平台不够：两个平台表现完全没变，
            // 其中一个挂掉一半就能让总数从 50% 涨到 60%。
            [
              composition ? `${den.n_valid} = ${composition}` : null,
              unusable > 0
                ? `共 ${den.n_total_responses} 条响应，${unusable} 条不可用`
                : `共 ${den.n_total_responses} 条响应，全部可用`,
            ]
              .filter(Boolean)
              .join(' · ')
          }
          alert={unusable > 0}
        />

        <ReadoutRate
          label="提及率"
          gloss="本品被提及的样本数 / 有效样本数"
          m={brand.m_mentioned}
          n={den.n_valid}
          live={live}
        />

        {/* m_first 取不到时走降级态，**不许当 0** ——
            「一次都没排第一」和「这个数还取不到」是完全不同的结论。 */}
        {brand.m_first === undefined ? (
          <ReadoutBlank
            label="首位提及率"
            gloss="出场顺位为 1 的样本数 / 被提及的样本数"
            reason="暂无排名数据"
            note="counts 未返回 m_first，后端上线该字段后自动恢复"
          />
        ) : (
          <ReadoutRate
            label="首位提及率"
            gloss="出场顺位为 1 的样本数 / 被提及的样本数。是位置事实，不是「AI 首推」"
            m={brand.m_first}
            n={brand.m_mentioned}
            live={live}
          />
        )}

        <ReadoutCount
          label="覆盖缺口"
          gloss="本品缺席或明显落后、且竞品在场的提问数"
          value={gaps.length}
          note={`共 ${rows.length} 条提问`}
          alert={gaps.length > 0}
        />
      </Instrument>

      <Plate
        title="逐提问"
        subtitle="上面那个总提及率是这些道平均出来的 —— 它可能由几条满分加几条挂零构成。每道的格数就是那条提问采了几次。"
      >
        <TraceBars data={bars} />
      </Plate>

      {/* 分平台表现（§4.0 第 2 条）—— 它直接回答多平台带来的唯一新信息：
          「我在哪个平台上不行」。单平台时不渲染，界面不该多出无意义的面板。 */}
      {multiPlatform ? (
        <Plate
          title="分平台"
          subtitle="上面的总提及率是这些平台混算出来的 —— 运营要知道的是「我在哪个平台上不行」"
        >
          <TraceBars data={platformBars(slices)} />
        </Plate>
      ) : null}

      <Plate
        title="覆盖缺口"
        subtitle="本品缺席或明显落后、而竞品在场的提问。右侧数字是失分量：竞品合计比本品多拿的提及次数"
        right={
          // 这是这个产品唯一可直接执行的产出 —— 在此之前只能截图发给推流团队
          <ExportGapsButton
            rows={gapCsvRows({ gaps, promptText, brandName: brandNames })}
            fileName={gapCsvFileName(taskName, run.id, run.created_at)}
            disabled={gaps.length === 0}
          />
        }
      >
        <GapList
          gaps={gaps}
          promptText={promptText}
          brandName={brandNames}
          totalPrompts={rows.length}
        />
      </Plate>

      <Plate flush>
        <div style={{ padding: 'var(--sp-5) var(--sp-6) 0' }}>
          <div className={runs.tabs} role="tablist">
            {[
              { id: 'matrix', label: '命中矩阵', count: matrixRows.length },
              // 计数用**总响应数**而不是 n_valid：样本表把不可用的那些也列出来
              // （罩着斜纹、标着「不进分母」），tab 上的数字必须和表里的行数对得上
              { id: 'samples', label: '样本列表', count: den.n_total_responses },
            ].map((t) => (
              <button
                key={t.id}
                role="tab"
                aria-selected={t.id === tab}
                className={`${runs.tab} ${t.id === tab ? runs.tabOn : ''}`}
                onClick={() => setTab(t.id)}
              >
                {t.label}
                <span className={runs.tabCount}>{t.count}</span>
              </button>
            ))}
          </div>
        </div>

        <div style={{ padding: '0 var(--sp-6) var(--sp-5)' }}>
          {tab === 'matrix' ? (
            <>
              {/* **命中矩阵强制单平台**（§4.0 第 3 条）：加一维就是三维，
                  而三维矩阵不可读。默认落在第一个平台。 */}
              {multiPlatform ? (
                <div className={runs.filters}>
                  <span className={runs.filterLabel}>平台</span>
                  {slices.map((s) => (
                    <button
                      key={s.code}
                      type="button"
                      className={runs.chip}
                      aria-pressed={s.code === activePlatform}
                      onClick={() => setActivePlatform(s.code)}
                    >
                      {s.label}
                    </button>
                  ))}
                  {/* 切平台时哪些面板跟着变、哪些不变，上一版只写在代码注释里，
                      界面上一个字都没有 —— 而这正是最容易让人对不上数的地方 */}
                  <span className={runs.reason} style={{ maxWidth: 'none' }}>
                    只有这张矩阵跟着切；上面的缺口清单是跨平台合计的
                  </span>
                </div>
              ) : null}
              {multiPlatform && !byPromptOnePlatform ? (
                <Pending height={220} />
              ) : (
                <>
                  <HitGrid rows={matrixRows} columns={columns} />
                  <Notation
                    entries={[
                      { swatch: 'var(--tick-on)', label: '本品命中' },
                      { swatch: 'var(--tick-other)', label: '竞品命中' },
                      { swatch: 'var(--tick-off)', label: '未提及（真实的 0）' },
                      { swatch: 'zero', label: '本品挂零' },
                      { swatch: 'void', label: '无有效样本，算不出' },
                    ]}
                    note="格内为 命中数 / 有效样本数"
                  />
                </>
              )}
            </>
          ) : (
            <SamplesPanel runId={runId} ownBrandId={brandId} taskId={taskId} />
          )}
        </div>
      </Plate>
    </div>
  )
}
