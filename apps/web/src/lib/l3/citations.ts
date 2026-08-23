/**
 * L3 纯函数 —— 引用域名榜的派生（口径见 `docs/API.md` §4）。
 *
 * 铁律同 `rates.ts`：不碰 fetch、不碰 React。
 *
 * ## 这个模块存在的唯一理由：榜单会撒谎
 *
 * 后端按**引用次数**累加排序（一个域名在一条回答里被引 3 次就计 3）。
 * 这个口径对聚合型站点有系统性偏向，而且在真实数据里看得见：
 *
 *     www.toutiao.com   9 次引用，只来自 **4** 条样本
 *     www.163.com      12 次引用，来自 **12** 条样本
 *
 * 只看名次，toutiao 紧跟在 163 后面，像是同一量级的存在。
 * 但 163 是**在 12 条不同的回答里各被引一次**，toutiao 是**在 4 条里被反复引**。
 * 对「我要去哪些站铺内容」这个问题，前者的覆盖面大得多。
 *
 * 所以榜单必须同时给出这两个数，并把「集中」这件事标出来 ——
 * 而不是让读者自己去做除法。
 */
import type { CitationDomain, CitationDomainsResult } from '@/lib/types'

export interface CitationRow extends CitationDomain {
  /** 名次，从 1 起。按后端给的顺序 —— 不在前端重排 */
  rank: number
  /**
   * 平均每条样本引了它几次。`n_samples` 为 0 时是 `null`（不可算）。
   *
   * 后端保证 `n_samples >= 1` 才会出现在榜上，但这里不假设 ——
   * 一个 0 分母在这个产品里必须显示成「算不出」，不是 0。
   */
  perSample: number | null
  /**
   * **集中引用**：平均每条样本引它 2 次以上，且总数够多（≥3）。
   *
   * 阈值是这么定的：`n_citations >= 2 * n_samples` 意味着「同一条回答里
   * 反复引同一个站」是常态而非偶然。总数下限 3 是为了挡住 2/1 这种
   * 小样本噪音 —— 一条回答里引了两次，说明不了任何事。
   */
  concentrated: boolean
}

export function citationRows(result: CitationDomainsResult): CitationRow[] {
  return result.items.map((item, i) => ({
    ...item,
    rank: i + 1,
    perSample: item.n_samples > 0 ? item.n_citations / item.n_samples : null,
    concentrated: item.n_citations >= 3 && item.n_citations >= 2 * item.n_samples,
  }))
}

export interface CitationCoverage {
  /** 榜上这几行加起来有多少次引用 */
  listed: number
  /** 全集有多少次引用 —— **这才是分母** */
  total: number
  /** 全集有多少个域名 */
  domains: number
  /** 榜上这几行占全集的比例；`total` 为 0 时是 `null` */
  share: number | null
  /** 榜单是不是被 limit 截断了 */
  truncated: boolean
}

/**
 * 榜单覆盖了全集的多少。
 *
 * ⚠️ 存在的理由写在 API.md §4：`n_citations` / `n_domains` 描述的是**全集**，
 * 不是 `items` 那几行。带 `limit` 时 `Σ items[].n_citations < n_citations`
 * 是正常的 —— **别拿 items 的和当分母**。这个函数把两个数都算出来，
 * 好让界面能明说「这 20 行是 144 次里的 108 次」，而不是让人以为看到了全部。
 */
export function citationCoverage(result: CitationDomainsResult): CitationCoverage {
  const listed = result.items.reduce((sum, x) => sum + x.n_citations, 0)
  const total = result.n_citations
  return {
    listed,
    total,
    domains: result.n_domains,
    share: total > 0 ? listed / total : null,
    truncated: listed < total,
  }
}

/**
 * 画条形图用的最大值。
 *
 * **用榜首的引用次数，不用全集总数** —— 榜首那行必须画满，否则整张图
 * 挤在左边一小截。返回 0 表示没有可画的东西。
 */
export function citationScaleMax(rows: CitationRow[]): number {
  return rows.reduce((max, r) => Math.max(max, r.n_citations), 0)
}
