import type { CrawlJob, FailureKind } from '@/lib/types'

/**
 * 采样失败的原因分布。
 *
 * ## 为什么值得单列一层
 *
 * 界面此前只说「另有 N 条采样失败」。但七类失败的**下一步动作完全不同**：
 * `login_required` 要人去换 storage_state，`rate_limited` 等一等就行，
 * `parse_error` 是页面 DOM 变了、得改选择器。只报一个数字等于把
 * 「该做什么」这件事留给读者去猜。
 *
 * ## 这一层守住的那条口径
 *
 * **`null` 不是 `unknown`**（`docs/API.md` §8.0.1 明确要求）：
 *
 *   · `null`    = 还没失败过 —— 一条 `status=failed` 却带 `null` 的 job
 *                 意味着**后端没给分类**，那本身是个异常，不该被算进任何一类
 *   · `unknown` = 失败了，但没认出是哪一类
 *
 * 把两者显示成同一个词，排查方向会直接跑偏：前者去查后端为什么没分类，
 * 后者去看 `error_message` 原文。所以这里把它们分成两个字段返回，
 * 调用方想合并也得自己动手。
 */

export interface FailureGroup {
  kind: FailureKind
  count: number
  /** 界面上的短标签 */
  label: string
  /** 下一步该做什么。空字符串表示「没有可做的，等就行」 */
  action: string
  /** 后端会不会自动重试 —— 会的话人就不必立刻动手 */
  autoRetried: boolean
}

const KIND_META: Record<FailureKind, { label: string; action: string; autoRetried: boolean }> = {
  timeout: {
    label: '超时',
    action: '后端会自动重试。冷启动被限流最常见的表现就是它，多半会自己好。',
    autoRetried: true,
  },
  rate_limited: {
    label: '被限流',
    action: '后端会自动退避重试。连续几次运行都出现的话，就得把采样频率降下来。',
    autoRetried: true,
  },
  login_required: {
    label: '登录态过期',
    action: '**要人去换 storage_state**，自动重试救不了 —— 重试多少次都还是没登录。',
    autoRetried: false,
  },
  platform_unavailable: {
    label: '平台没接',
    action: '这个平台的 provider 还没实现。把它从任务的平台集里去掉，否则每次都白跑。',
    autoRetried: false,
  },
  parse_error: {
    label: '抽不出答案',
    action: '页面拿到了但没抽出内容 —— 多半是对方改了 DOM，要改选择器。',
    autoRetried: false,
  },
  worker_died: {
    label: 'worker 中途没了',
    action: '僵死回收收的。偶发可以忽略；反复出现要去看采集节点。',
    autoRetried: false,
  },
  unknown: {
    label: '没认出原因',
    action: '后端没能归类。要看这条 job 的 error_message 原文，在 /qa 里。',
    autoRetried: false,
  },
}

/** 排序权重：**要人动手的排前面**，能自愈的排后面。 */
const URGENCY: FailureKind[] = [
  'login_required',
  'parse_error',
  'platform_unavailable',
  'worker_died',
  'unknown',
  'rate_limited',
  'timeout',
]

export interface FailureBreakdown {
  groups: FailureGroup[]
  /** 参与分类的失败总数（不含没分类的那些） */
  classified: number
  /**
   * `status=failed` 但 `failure_kind` 是 null 的条数。
   *
   * **这不是「未知原因」** —— 那是 `unknown`。这里是后端压根没给分类，
   * 属于后端异常，界面要单独说，别混进 `unknown` 里。
   */
  unclassified: number
}

export function failureBreakdown(jobs: CrawlJob[]): FailureBreakdown {
  const counts = new Map<FailureKind, number>()
  let unclassified = 0

  for (const j of jobs) {
    // 只看真的失败了的 —— pending/running 的 job 带 failure_kind 是上一次尝试
    // 留下的痕迹（退避中），不是这次的结论
    if (j.status !== 'failed') continue
    if (j.failure_kind === null) {
      unclassified += 1
      continue
    }
    counts.set(j.failure_kind, (counts.get(j.failure_kind) ?? 0) + 1)
  }

  const groups: FailureGroup[] = []
  for (const kind of URGENCY) {
    const count = counts.get(kind)
    if (!count) continue
    groups.push({ kind, count, ...KIND_META[kind] })
  }

  return {
    groups,
    classified: groups.reduce((n, g) => n + g.count, 0),
    unclassified,
  }
}

/**
 * 这批失败里有没有「等不来自愈」的。
 *
 * 用来决定要不要把提示的语气从「提醒」抬到「警告」——
 * 全是 timeout / rate_limited 的话人不必立刻做什么。
 */
export function needsHumanAction(b: FailureBreakdown): boolean {
  return b.groups.some((g) => !g.autoRetried) || b.unclassified > 0
}

/**
 * 退避中的采样条数。
 *
 * 一条正在等退避的 job **状态仍是 `pending`**（API.md §8.0.2，自动重试不新增
 * 状态值），靠 `next_attempt_at` 在未来来识别。不数出来的话，
 * 界面会把「正在自动重试」显示成「还没轮到」，读者以为卡住了。
 */
export function backoffPending(jobs: CrawlJob[], now: Date = new Date()): number {
  let n = 0
  for (const j of jobs) {
    if (j.status !== 'pending' || !j.next_attempt_at) continue
    if (new Date(j.next_attempt_at).getTime() > now.getTime()) n += 1
  }
  return n
}
