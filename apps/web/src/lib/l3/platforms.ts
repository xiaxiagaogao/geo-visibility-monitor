/**
 * L3 纯函数 —— 多平台口径（P2-09，规范见 `docs/PHASE2.md` §4.0）。
 *
 * 拍板结论：**平台是筛选器；「全部平台」保留混算的总数，但把分母的构成摊开。**
 *
 * 铁律同 `rates.ts`：入参只有整数计数，不碰 fetch、不碰 React。
 */
import type { BarDatum, CountsResponse, PlatformOption } from '../types'

/** 一个平台在本次 run 里的切片。 */
export interface PlatformSlice {
  code: string
  label: string
  nValid: number
  mMentioned: number
  mFirst: number
}

/**
 * 把 `counts?group_by=platform` 的 `series` 翻成按平台的切片。
 *
 * **顺序跟 `/v1/config/platforms`，不跟 `series` 的返回顺序** —— 后端不保证
 * 数组顺序稳定，而顺序一跳用户会以为数据变了。同 `Brand.competitor_ids`
 * 那条纪律（`types.ts`：不许拿数组下标当顺序）。
 *
 * **认不出来的平台代码保留原样、排在最后**，绝不丢弃：后端加了平台而前端
 * 配置还没刷新时，丢掉那段样本会让分母对不上 —— 而分母对不上是最难查的一类。
 */
export function platformSlices(
  counts: CountsResponse,
  options: PlatformOption[],
): PlatformSlice[] {
  const byKey = new Map(counts.series.map((b) => [b.key, b]))
  const out: PlatformSlice[] = []

  const take = (code: string, label: string) => {
    const b = byKey.get(code)
    if (!b) return
    byKey.delete(code)
    out.push({
      code,
      label,
      nValid: b.denominator.n_valid,
      mMentioned: b.brand.m_mentioned,
      mFirst: b.brand.m_first ?? 0,
    })
  }

  for (const o of options) take(o.code, o.label)
  for (const key of [...byKey.keys()]) take(key, key)   // 认不出来的，用代码当标签

  return out
}

/**
 * KPI 分母行的构成（`35 = DeepSeek 30 + 通义千问 5`）。
 *
 * §4.0 第 1 条：单平台时 `21/35` 够了，多平台时不够 —— **构成才决定这个数的
 * 含义**。两个平台表现完全没变，其中一个挂掉一半就能让总数从 50% 涨到 60%；
 * 摊开之后任何人一眼看出「是分母的构成变了，不是表现变了」。
 *
 * **单平台返回空数组** —— 界面不该凭空多一行没有信息量的东西。
 */
export function denominatorParts(slices: PlatformSlice[]): { label: string; n: number }[] {
  if (slices.length <= 1) return []
  return slices.map((s) => ({ label: s.label, n: s.nValid }))
}

/**
 * 「分平台表现」面板的数据。
 *
 * **每根条都是本品**（只是分平台看），所以全部 `own: true` ——
 * 这个面板里没有竞品，配色不需要区分主角。
 *
 * **分母为 0 的平台照样出条**：`rate(m, 0)` 是 `null`，UI 画成 `—`，
 * 语义是「这个平台没采到」。过滤掉才是错的 —— 用户会以为压根没跑那个平台。
 */
export function platformBars(slices: PlatformSlice[]): BarDatum[] {
  return slices.map((s) => ({
    key: s.code,
    label: s.label,
    m: s.mMentioned,
    n: s.nValid,
    own: true,
  }))
}
