import { Fragment, type ReactNode } from 'react'

export interface Highlight {
  /** 命中在 full_text 里的字符下标 */
  offset: number
  /** 实际匹配到的字面（别名可能与品牌名不同，比如「361°」之于「361度」） */
  matchedTerm: string
}

/**
 * L0 全文，命中处内联高亮。
 *
 * ⚠️ `highlights` 现在恒为空数组 —— 后端还给不出 offset：
 * `match_brand` 算出了 offset 与 matched_term，但 `annotate.py` 切完
 * evidence_snippet 就把它们丢了，`mentions` 表**根本没有这两列**（docs/29 §5.2）。
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

  for (const [i, h] of sorted.entries()) {
    if (h.offset < cursor) continue // 重叠命中：以先出现的为准
    if (h.offset > cursor) {
      parts.push(<Fragment key={`t${i}`}>{text.slice(cursor, h.offset)}</Fragment>)
    }
    const end = h.offset + h.matchedTerm.length
    parts.push(
      <mark key={`h${i}`} className={markClassName}>
        {text.slice(h.offset, end)}
      </mark>,
    )
    cursor = end
  }
  if (cursor < text.length) parts.push(<Fragment key="tail">{text.slice(cursor)}</Fragment>)

  return <div className={className}>{parts}</div>
}
