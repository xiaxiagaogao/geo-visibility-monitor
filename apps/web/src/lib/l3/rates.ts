/**
 * L3 纯函数 —— 从 L2 的整数 counts 派生比率。
 *
 * 铁律（API.md §4.1、§4.2）：
 *   · 入参只有整数计数，出参 `number | null`
 *   · `null` 表示**不可算**（分母为 0），由 UI 决定显示 `—`
 *   · `0` 表示**真的是 0** —— 土巴兔的 0.0% 是真实结论，不是缺数据
 *   · 不碰 fetch、不碰 React
 *
 * SoV 已砍掉：它需要显著度加权 + 时序，两样都缺。想找它去 git history。
 */

/** 比率 = m / n。n <= 0 → null（无分母不许显示 0%） */
export function rate(m: number, n: number): number | null {
  if (!Number.isFinite(m) || !Number.isFinite(n)) return null
  if (n <= 0) return null
  return m / n
}

/** 头部位置占比 = m_head / m_mentioned。次级指标，不进 KPI 行 ——
 *  它和首位提及率含义相近（篇幅前 1/3 vs 顺位第 1），都摆顶上会互相稀释 */
export function headShare(mHead: number, mMentioned: number): number | null {
  return rate(mHead, mMentioned)
}

/**
 * 首位提及率 = 本品出场顺位为 1 的样本数 / 本品被提及的样本数。
 *
 * **不叫「首推率」**：我们的 rank 是出场顺位，只知道它第一个被提到，
 * 不知道是不是被推荐。名字必须 match 口径。
 */
export function firstMentionRate(mFirst: number, mMentioned: number): number | null {
  return rate(mFirst, mMentioned)
}

/** 矩阵格的色阶档位。0 命中是空心格，不是最暗档。 */
export type MatrixLevel = 'zero' | 'l1' | 'l2' | 'l3'

export function matrixLevel(r: number | null): MatrixLevel {
  if (r === null || r <= 0) return 'zero'
  if (r <= 1 / 3) return 'l1'
  if (r <= 2 / 3) return 'l2'
  return 'l3'
}

/** 比率 → 显示文本。null → `—`，其余保留 1 位小数。 */
export function formatRate(r: number | null): string {
  if (r === null) return '—'
  return `${(r * 100).toFixed(1)}%`
}

/**
 * 分母文本。**凡出现比率，必须同时显示 m / n**（API.md §4.2 第 4 条）——
 * 孤零零的百分比在这个产品里没有可信度。
 */
export function formatFraction(m: number, n: number): string {
  return `${m} / ${n}`
}
