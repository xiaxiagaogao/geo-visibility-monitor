/**
 * 样本行的派生状态 —— 「这一条回答对本品来说是什么结果」。
 *
 * 只有一件事值得单独成层：**四种状态里有两对长得像、含义完全不同**，
 * 而两次都是「把降级态当成结论」这一类错：
 *
 *   · `none`（标注过，本品没被提到）  vs  `unannotated`（还没标注，不知道）
 *   · `citationOnly`（只出现在引用里） vs  `body`（正文里真被提到了）
 *
 * 把 `unannotated` 显示成「未提及」，等于把「我们还没算」说成「AI 没提你」——
 * 一个是我们的问题，一个是客户的问题，说反了就是编结论。
 *
 * 纯函数，不碰 fetch 与 React。
 */
import type { Mention, RawResponseSummary } from '../types'

export type SampleHitKind = 'body' | 'citationOnly' | 'none' | 'unannotated'

export interface SampleHit {
  kind: SampleHitKind
  /**
   * 出场顺位（1-based）。**是位置事实，不是推荐名次**（API.md §7.1）——
   * 只有 `body` 命中才有值，`citationOnly` 是 null（正文里没出现）。
   */
  rank: number | null
  /** 命中处前后各 40 字，取自后端标注，不是前端切的 */
  snippet: string | null
}

/** 本品在这条样本里的命中情况。`mentions` 里没有本品那条时看有没有标注过。 */
export function ownHit(sample: RawResponseSummary, ownBrandId: number): SampleHit {
  const mine: Mention | undefined = sample.mentions.find((m) => m.brand_id === ownBrandId)

  if (!mine) {
    // 标注过、但本品这条 mention 不存在，说明这条样本里本品确实没出现
    // （annotate 会给每个被监测品牌都写一行）。没标注过则是「还不知道」。
    return {
      kind: sample.annotator_version ? 'none' : 'unannotated',
      rank: null,
      snippet: null,
    }
  }

  if (!mine.mentioned) return { kind: 'none', rank: null, snippet: null }
  if (mine.mention_type === 'citation_only') {
    return { kind: 'citationOnly', rank: null, snippet: mine.evidence_snippet }
  }
  return { kind: 'body', rank: mine.position_rank, snippet: mine.evidence_snippet }
}

/**
 * 这条样本进不进分母。
 *
 * `answer_status !== 'ok'` 的样本（empty / too_short / error）**采到了但不可用**，
 * 分母口径是 `n_valid = ok 的条数`（API.md §4）。列表里必须标出来，
 * 否则用户会拿「表里 35 行」去对「有效样本 31」，然后以为哪边算错了。
 */
export function isValidSample(sample: RawResponseSummary): boolean {
  return sample.answer_status === 'ok'
}

/** 正文被截断了没有 —— `text_preview` 只有前 160 字。 */
export function isPreviewTruncated(sample: RawResponseSummary): boolean {
  return sample.text_length > sample.text_preview.length
}

/**
 * 分页的人话：`第 1–20 条 / 共 35 条`。
 *
 * `total` 为 0 时返回 null，让调用方走空态 —— 「第 1–0 条」是个笑话。
 */
export function pageLabel(offset: number, pageCount: number, total: number): string | null {
  if (total <= 0 || pageCount <= 0) return null
  const from = offset + 1
  const to = offset + pageCount
  return `第 ${from}–${to} 条 / 共 ${total} 条`
}
