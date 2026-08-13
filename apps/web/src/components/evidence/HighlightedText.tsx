import { Fragment, type ReactNode } from 'react'

import { codePointLength, toCodePoints } from '@/lib/l3/text'

export interface Highlight {
  /** 命中在 full_text 里的字符下标 */
  offset: number
  /** 实际匹配到的字面（别名可能与品牌名不同，比如「361°」之于「361度」） */
  matchedTerm: string
  /**
   * 这一处单独的样式，不给就用 `markClassName`。
   *
   * 有它才能把本品和竞品染成两种底色。**没有做成 `own?: boolean`** ——
   * 这个组件不该知道「本品」是什么，那是调用方的领域概念。
   */
  className?: string
  /** 悬停提示，通常是「哪个品牌 · 靠哪个别名命中的」 */
  title?: string
}

/**
 * L0 全文，命中处内联高亮。
 *
 * ⚠️ `highlights` 现在恒为空数组，但**原因已经不是后端给不出**：
 * 写这个组件时 `mentions` 表确实没有 offset 列，后来后端补上了 ——
 * `MentionOut` 现在有 `first_offset` 与 `matched_term`（API.md §7）。
 * 空数组只是因为本轮还吃固定数据，接上 API 就有值。
 *
 * 接的时候按 API.md §7.1 那条不变量自检，错位会立刻暴露：
 *   full_text.slice(first_offset, first_offset + matched_term.length) === matched_term
 * 后端在全库 179 条命中上验过 179/179。
 * 注意字段名要映射：后端 `first_offset` / `matched_term` → 这里的 `offset` / `matchedTerm`。
 *
 * 这里**故意不做**「前端按 matched_term 自己在 full_text 里找」的兜底：
 * 那等于在前端重造一套匹配逻辑，会和 L1 的口径分叉，
 * 而这个产品的全部可信度就建立在「UI 上的数和 L1 标注是同一套」上面。
 */
export function HighlightedText({
  text,
  highlights = [],
  className,
  markClassName,
}: {
  text: string
  highlights?: Highlight[]
  className?: string
  markClassName?: string
}) {
  if (highlights.length === 0) {
    return <div className={className}>{text}</div>
  }

  const sorted = [...highlights].sort((a, b) => a.offset - b.offset)
  const parts: ReactNode[] = []
  let cursor = 0

  // **按码点切，不是 UTF-16 单元。** offset 来自后端（Python 的码点索引），
  // 用 String.slice 会在正文含 emoji 时错位 —— 一个 🏃 在 Python 里算 1、
  // 在 JS 里算 2。共用 lib/l3/text 的那两个函数，不在这儿再写一份。
  const cp = toCodePoints(text)

  for (const [i, h] of sorted.entries()) {
    if (h.offset < cursor) continue // 重叠命中：以先出现的为准
    if (h.offset > cursor) {
      parts.push(<Fragment key={`t${i}`}>{cp.slice(cursor, h.offset).join('')}</Fragment>)
    }
    const end = h.offset + codePointLength(h.matchedTerm)
    parts.push(
      <mark key={`h${i}`} className={h.className ?? markClassName} title={h.title}>
        {cp.slice(h.offset, end).join('')}
      </mark>,
    )
    cursor = end
  }
  if (cursor < cp.length) parts.push(<Fragment key="tail">{cp.slice(cursor).join('')}</Fragment>)

  return <div className={className}>{parts}</div>
}
