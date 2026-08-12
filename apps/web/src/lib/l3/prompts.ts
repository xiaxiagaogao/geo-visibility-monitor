/**
 * 提问词的分组与统计（A3）。
 *
 * `category` **没有服务端过滤参数**（API.md §6）—— 拿回全量自己归类。
 * 归类逻辑放这里而不是组件里，是因为它有两条容易写错的边界：
 * 未知类别不能吞掉，`null` 与空串要归到同一组。
 *
 * 纯函数，不碰 fetch 与 React。
 */
import type { Prompt } from '../types'

/**
 * 已知类别的中文名。
 *
 * **未知类别不映射成「其他」，原样显示。** 后端随时可能加新类别，
 * 映射不到就吞进「其他」的话，界面上会出现一堆看不出区别的行，
 * 而真相是它们分属不同类别。
 */
const CATEGORY_LABEL: Record<string, string> = {
  unprompted: '无提示提问',
  scenario: '场景提问',
}

/** `null` / 空串归到同一组的键 */
export const UNCATEGORIZED = ''

export function categoryLabel(category: string | null): string {
  const key = (category ?? '').trim()
  if (!key) return '未分类'
  return CATEGORY_LABEL[key] ?? key
}

export interface PromptGroup {
  category: string
  label: string
  prompts: Prompt[]
}

/**
 * 按类别分组，**组内保持入参顺序**（后端按 id 排，即创建顺序）。
 *
 * 组的顺序：已知类别按 `CATEGORY_LABEL` 的声明顺序在前，其余按首次出现，
 * 「未分类」永远排最后 —— 它不是一个类别，是「还没归类」。
 */
export function groupByCategory(prompts: Prompt[]): PromptGroup[] {
  const buckets = new Map<string, Prompt[]>()
  for (const p of prompts) {
    const key = (p.category ?? '').trim()
    const list = buckets.get(key)
    if (list) list.push(p)
    else buckets.set(key, [p])
  }

  const known = Object.keys(CATEGORY_LABEL).filter((k) => buckets.has(k))
  const rest = [...buckets.keys()].filter(
    (k) => k !== UNCATEGORIZED && !(k in CATEGORY_LABEL),
  )
  const ordered = [...known, ...rest]
  if (buckets.has(UNCATEGORIZED)) ordered.push(UNCATEGORIZED)

  return ordered.map((category) => ({
    category,
    label: categoryLabel(category || null),
    prompts: buckets.get(category) ?? [],
  }))
}

/**
 * 下一次运行会真的问出去的条数。
 *
 * **这就是提及率的分母来源**：`create_run` 只把 `is_active=true` 的提问词
 * 冻结进快照，每条再乘以采样数变成 job。所以「启用 0 条」意味着下次运行
 * 会是 `empty` 状态 —— 一条 job 都建不出来，那是配置问题不是采集失败。
 */
export function activeCount(prompts: Prompt[]): number {
  return prompts.filter((p) => p.is_active).length
}
