/**
 * 缺口清单 → CSV 行（P2-04）。
 *
 * 缺口清单是这个产品**唯一可直接执行的产出** —— 它回答「该去哪些提问下补内容」，
 * 输出直接交给推流团队。在此之前只能截图。
 *
 * 纯函数，不碰 fetch / React / DOM（下载动作在组件里）。
 */
import type { Gap, GapTier } from './gaps'
import { formatRate, rate } from './rates'

const TIER_LABEL: Record<GapTier, string> = {
  absent: '完全缺席',
  trailing: '明显落后',
}

const PRIORITY_LABEL: Record<string, string> = {
  high: '高',
  mid: '中',
  low: '低',
}

/**
 * 表头。
 *
 * **本品命中与有效样本是两列，不拼成 `3/5`。** Excel 会把 `3/5` 当成日期
 * 转成「3月5日」——一份发给别人的表格里出现这个，没人看得出原本是个分数。
 * 拆成两列既躲开了转换，也让收表的人能直接排序和求和。
 */
export const GAP_CSV_HEADER = [
  '提问',
  '缺口类型',
  '本品命中',
  '有效样本',
  '本品提及率',
  '失分量',
  '优先级',
  '在场竞品',
] as const

/**
 * 一条缺口一行。
 *
 * 「失分量」= Σ max(0, 竞品命中 − 本品命中)，读作「在这条提问下，竞品合计比
 * 本品多拿了多少次提及」。它是排序依据，所以必须出现在导出里 ——
 * 否则收表的人只能按缺口类型分组，而那个分不出轻重。
 */
export function gapCsvRows(params: {
  gaps: Gap[]
  /** promptId → 提问正文，取自 run 快照 */
  promptText: Map<number, string>
  /** brandId → 品牌名，取自 run 快照（竞品被删了名字也还在） */
  brandName: Map<number, string>
}): (string | number)[][] {
  const { gaps, promptText, brandName } = params
  return [
    [...GAP_CSV_HEADER],
    ...gaps.map((g) => [
      promptText.get(g.promptId) ?? `提问 #${g.promptId}`,
      TIER_LABEL[g.tier],
      g.ownM,
      g.n,
      formatRate(rate(g.ownM, g.n)),
      g.score,
      PRIORITY_LABEL[g.priority] ?? g.priority,
      // 竞品名 + 命中数写在一格里。名字在前，所以不会被 Excel 当成分数或日期
      g.competitorsPresent
        .map((c) => `${brandName.get(c.brandId) ?? `#${c.brandId}`} ${c.m ?? 0}`)
        .join(' · '),
    ]),
  ]
}

/**
 * 文件名 —— **上下文全靠它承载**。
 *
 * 元信息（任务名 / 哪次运行 / 导出时间）不写进 CSV 正文：在表头上面加几行
 * 说明会让 Excel 的「排序」「筛选」选错范围，而这张表的用途正是排序筛选。
 * 一份脱离上下文的缺口清单没法用，所以上下文进文件名。
 */
export function gapCsvFileName(taskName: string, runId: number, isoDate: string): string {
  return `缺口清单_${taskName}_run${runId}_${isoDate.slice(0, 10)}.csv`
}
