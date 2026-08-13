/**
 * 证据页的高亮 —— 把 L1 标注映射成「原文里该给哪几段加底色」。
 *
 * 这一层存在的唯一理由是**那条可自检的不变量**（API.md §7.1）：
 *
 *   按**码点**切 full_text[first_offset : first_offset + len(matched_term)] === matched_term
 *
 * ⚠️ 这条**不能**写成 `full_text.slice(...)` —— API.md 原来就是那么写的，
 * 而那个写法在 JS 里是错的：`slice` 按 UTF-16 单元，offset 却是 Python 的
 * 码点索引。正文里有一个 emoji，它就开始错位。（文档已同步更正。）
 *
 * 后端在全库 179 条命中上验过 179/179 —— 那是 Python 侧的验证，成立；
 * 错的是「前端可以照抄这个表达式」这个假设。前端在渲染前再验一次，
 * 因为一旦它不成立，页面**不会报错**，只会把底色画在错误的字上 ——
 * 而这个产品的全部可信度就建立在「UI 上标出来的就是 L1 数过的那一处」。
 * 静默画错比空着糟得多：用户会拿一段错的原文去跟客户解释结论。
 *
 * 所以对不上的那条**不画**，而是单独返回，由 UI 明说「这条对不上」。
 *
 * **不做 indexOf 兜底。** 拿 matched_term 自己去 full_text 里找，等于在前端
 * 重造一套匹配逻辑（大小写折叠、别名优先级规则都在后端），口径当场分叉。
 * 找到的那一处很可能不是 L1 数的那一处，而页面看起来完全正常。
 *
 * 纯函数，不碰 fetch 与 React。
 */
import type { Mention } from '../types'

import { codePointLength, toCodePoints } from './text'

export interface EvidenceHighlight {
  brandId: number
  /** 命中在 full_text 里的字符下标 */
  offset: number
  matchedTerm: string
  /** 本品还是竞品 —— 决定底色，读者只关心「我在哪」 */
  own: boolean
}

/** 不变量没成立的一条。**要显示出来，不能吞掉。** */
export interface EvidenceMismatch {
  brandId: number
  offset: number
  /** 标注说命中的字面 */
  expected: string
  /** 按 offset 切出来实际是什么 —— 空串表示 offset 已经越过正文末尾 */
  actual: string
}

export interface EvidenceHighlights {
  highlights: EvidenceHighlight[]
  mismatches: EvidenceMismatch[]
}

/**
 * 从标注构建高亮。
 *
 * 三种**不是错误**、只是没有正文位置的情况，直接跳过，不进 mismatches：
 *   · `mentioned === false`   这个品牌根本没被提到
 *   · `first_offset === null` `citation_only` 命中，正文里没出现
 *   · `matched_term === null` 同上
 */
export function buildHighlights(
  fullText: string,
  mentions: Mention[],
  ownBrandId: number,
): EvidenceHighlights {
  const highlights: EvidenceHighlight[] = []
  const mismatches: EvidenceMismatch[] = []
  // 切一次，循环里复用。**按码点，不是 UTF-16 单元** —— 见 toCodePoints 的注释
  const cp = toCodePoints(fullText)

  for (const m of mentions) {
    if (!m.mentioned) continue
    // **必须显式判 null。** `if (!m.first_offset)` 会把 offset === 0 吃掉，
    // 而 0 是正文第一个字 —— 最容易漏、也最难发现的那一档。
    if (m.first_offset === null || m.matched_term === null) continue

    const end = m.first_offset + codePointLength(m.matched_term)
    const actual = cp.slice(m.first_offset, end).join('')

    if (actual !== m.matched_term) {
      mismatches.push({
        brandId: m.brand_id,
        offset: m.first_offset,
        expected: m.matched_term,
        actual,
      })
      continue
    }

    highlights.push({
      brandId: m.brand_id,
      offset: m.first_offset,
      matchedTerm: m.matched_term,
      own: m.brand_id === ownBrandId,
    })
  }

  // 按 offset 升序 —— HighlightedText 靠这个顺序切片。
  // 同 offset 时本品排前面：重叠命中它只取第一个，本品被竞品盖掉最难解释。
  return {
    highlights: highlights.sort((a, b) => a.offset - b.offset || Number(b.own) - Number(a.own)),
    mismatches,
  }
}

/**
 * 出场顺序（按 offset 升序的品牌列表）——「谁先被提到」。
 *
 * 和 `position_rank` **算的是同一件事，但这里是从当前这条样本现算的**，
 * 用来在证据页上把 rank 变成看得见的顺序。两者对不上就是标注漂了。
 */
export function mentionOrder(highlights: EvidenceHighlight[]): number[] {
  const seen = new Set<number>()
  const order: number[] = []
  for (const h of highlights) {
    if (seen.has(h.brandId)) continue
    seen.add(h.brandId)
    order.push(h.brandId)
  }
  return order
}
