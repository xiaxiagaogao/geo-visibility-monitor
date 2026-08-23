/**
 * L3 纯函数 —— 跨 run 的时间序列与**口径断点**。
 *
 * 铁律同 `rates.ts`：不碰 fetch、不碰 React。
 *
 * ## 为什么这个模块的重点是「断点」而不是「趋势」
 *
 * README §5 曾把跨 run 趋势列在「明确不做」里，理由是「目前只有一个采集日，
 * 画出来是假的」。**那条理由已经不成立** —— 任务 27 现在有 12 次 run
 * （2026-08-16 ~ 08-23）。但它换成了一个更麻烦的问题：
 *
 * 这 12 次**不是在同一个口径下采的**。deepseek 中途从任务里摘掉了、
 * P2-37 上线了联网标注、节奏打散改过。把它们连成一条平滑的线，
 * 就是把**口径变化伪装成表现变化** —— 而 run 快照这套机制存在的全部理由
 * 就是防止这件事（README §2.1）。
 *
 * 所以这个模块的产出不是「一条线」，是「几段线 + 中间的断口」。
 *
 * ## 断点判据（只用真的拿得到的信号）
 *
 * 1. **平台集变了** —— 硬信号。`Run.platforms` 是 run 自己的快照，
 *    列表接口就带着，不用额外取数。平台一换，分母的构成就换了。
 * 2. **这次 run 带了运行说明（note）** —— 软信号。note 是自由文本，
 *    解析它去猜口径变化是不可靠的；但「有人专门为这次运行写了说明」
 *    本身就值得读者停一下，所以标出来、把原文给他看，**不替他下结论**。
 *
 * ⚠️ **提问集的变化检测不到。** 那需要逐 run 取 `RunDetail` 快照
 * （12 次 run 就是 12 个额外请求）。所以这条线**不保证**两段一定可比 ——
 * 界面上必须把这个限度说出来，不能让人以为没断口就等于口径没变。
 */
import type { CountsResponse, Run, RunStatus } from '@/lib/types'

import { rate } from './rates'

/** 断口的原因。`note` 是软信号 —— 它不断言口径变了，只说「这里有话要读」。 */
export type BreakKind = 'platforms' | 'note'

export interface TrendPoint {
  runId: number
  /** ISO 字符串，原样带出 —— 格式化是表现层的事 */
  at: string
  status: RunStatus
  /** 本品被提及的样本数 */
  m: number
  /** 有效样本数（分母） */
  n: number
  /** `null` = 分母为 0，不可算。**不是 0** */
  r: number | null
  /**
   * 竞品区间：这一次运行里，竞品提及率的最低与最高。
   *
   * **画区间带而不是 7 条竞品线**，两个理由：7 条线在 130px 高的带子里
   * 是一团面条，读不出任何东西；而运营真正要问的是「我在场上处于什么位置」——
   * 那是一个区间问题，不是七个个体问题。
   *
   * 没有竞品、或竞品分母为 0 时是 `null` —— 不画一条贴地的带子冒充「竞品都是 0」。
   */
  competitorBand: { min: number; max: number } | null
  platforms: string[]
  note: string | null
  /**
   * 这次运行的分母不完整（partial / pending / running）。
   * 它的比率会偏高，不能和一次完整运行直接比 —— 和断点是两回事，所以分开标。
   */
  incomplete: boolean
  /**
   * 这一点与**前一点之间**发生了什么。断口画在它左边。
   * 第一个点永远是空数组（没有「前一点」）。
   */
  breaks: BreakKind[]
}

/** 把平台集归一成可比较的键 —— 顺序不保证，不能直接比数组 */
function platformKey(platforms: string[]): string {
  return [...platforms].sort().join('|')
}

const INCOMPLETE: ReadonlySet<RunStatus> = new Set<RunStatus>([
  'partial',
  'pending',
  'running',
])

/**
 * 把 run 列表与逐 run 的 counts 拼成时间序列。
 *
 * @param runs   任意顺序；输出**一律按 created_at 升序**（时间轴从左到右）
 * @param counts runId → 这次运行的 counts。**取不到的 run 直接不出现在结果里** ——
 *               在时间轴上补一个 0 会把「没取到」画成「这次是 0%」，
 *               那是这套界面最不该犯的错。
 */
export function buildTrend(
  runs: Run[],
  counts: ReadonlyMap<number, CountsResponse>,
): TrendPoint[] {
  const ordered = [...runs]
    .filter((r) => counts.has(r.id))
    .sort((a, b) => Date.parse(a.created_at) - Date.parse(b.created_at))

  return ordered.map((run, i) => {
    const c = counts.get(run.id)!
    const n = c.denominator.n_valid
    const m = c.brand.m_mentioned

    const breaks: BreakKind[] = []
    if (i > 0) {
      const prev = ordered[i - 1]
      if (platformKey(prev.platforms) !== platformKey(run.platforms)) {
        breaks.push('platforms')
      }
    }
    // note 是这一次运行自己的说明，第一个点也可以有
    if (run.note && run.note.trim()) breaks.push('note')

    // 竞品区间。**同一个分母** —— counts 的 denominator 对本品与竞品是同一个，
    // 所以这里不会出现「拿不同分母的比率比大小」。
    const compRates = c.competitors
      .map((x) => rate(x.m_mentioned, n))
      .filter((x): x is number => x !== null)

    return {
      runId: run.id,
      at: run.created_at,
      status: run.status,
      m,
      n,
      r: rate(m, n),
      competitorBand: compRates.length
        ? { min: Math.min(...compRates), max: Math.max(...compRates) }
        : null,
      platforms: run.platforms,
      note: run.note,
      incomplete: INCOMPLETE.has(run.status),
      breaks,
    }
  })
}

/**
 * 时间轴上每个点的横坐标（0–1）。
 *
 * **按真实时间排，不按序号等距排。** 12 次 run 里有 5 次挤在同一天、
 * 另外几次隔了两三天；等距排会把「密集重测」和「隔天一测」画成同一件事。
 *
 * 全部时间相同（或只有一个点）时退化成等距 —— 除以 0 会得到 NaN，
 * 而一个 NaN 会让整条线消失。
 */
export function timeAxis(points: TrendPoint[]): number[] {
  if (points.length === 0) return []
  if (points.length === 1) return [0.5]

  const ts = points.map((p) => Date.parse(p.at))
  const min = Math.min(...ts)
  const max = Math.max(...ts)
  const span = max - min
  if (span <= 0) return points.map((_, i) => i / (points.length - 1))
  return ts.map((t) => (t - min) / span)
}

/**
 * 断口把序列切成几段可比的区间。
 *
 * **只有硬信号（平台集变化）切段。** note 是软信号，它提醒读者停一下，
 * 但不足以断言两段不可比 —— 拿它切段等于替读者下了一个我们没有依据的结论。
 */
export function comparableSegments(points: TrendPoint[]): TrendPoint[][] {
  const segments: TrendPoint[][] = []
  let current: TrendPoint[] = []

  for (const p of points) {
    if (p.breaks.includes('platforms') && current.length > 0) {
      segments.push(current)
      current = []
    }
    current.push(p)
  }
  if (current.length > 0) segments.push(current)
  return segments
}

/**
 * 这批点里有几次运行的分母是不完整的。
 * 用来决定要不要在图旁边挂那句「这几段比率会偏高」。
 */
export function incompleteCount(points: TrendPoint[]): number {
  return points.filter((p) => p.incomplete).length
}
