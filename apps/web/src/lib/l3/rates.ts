/**
 * L3 纯函数 —— 从 L2 的整数 counts 派生比率。
 *
 * 铁律（docs/21 §1、docs/27 §5.3）：
 *   · 入参只有整数计数，出参 `number | null`
 *   · `null` 表示**不可算**（分母为 0），由 UI 决定显示 `—`
 *   · `0` 表示**真的是 0**，绝不能和 null 混为一谈 ——
 *     土巴兔的 0.0% 是真实结论，不是缺数据
 *   · 不碰 fetch、不碰 React
 */

/** 提及率 = m / n。n <= 0 → null（无分母不许显示 0%） */
export function rate(m: number, n: number): number | null {
  if (!Number.isFinite(m) || !Number.isFinite(n)) return null
  if (n <= 0) return null
  return m / n
}

/** 头部位置占比 = m_head / m_mentioned */
export function headShare(mHead: number, mMentioned: number): number | null {
  return rate(mHead, mMentioned)
}

/** SoV = m_brand / (m_brand + Σ m_competitor)。分母 0 → null */
export function sov(mBrand: number, mCompetitors: readonly number[]): number | null {
  if (!Number.isFinite(mBrand)) return null
  const total = mCompetitors.reduce((acc, m) => acc + (Number.isFinite(m) ? m : 0), mBrand)
  return rate(mBrand, total)
}

/** 矩阵格子的色阶档位。0 命中是空心格，不是最暗档。 */
export type MatrixLevel = 'zero' | 'l1' | 'l2' | 'l3'

export function matrixLevel(r: number | null): MatrixLevel {
  if (r === null || r <= 0) return 'zero'
  if (r <= 1 / 3) return 'l1'
  if (r <= 2 / 3) return 'l2'
  return 'l3'
}

/** 比率 → 显示文本。null → `—`，其余保留 1 位小数（docs/23 §5.1）。 */
export function formatRate(r: number | null): string {
  if (r === null) return '—'
  return `${(r * 100).toFixed(1)}%`
}

/**
 * 分母文本。**凡出现比率必须同时显示 m / n**（docs/27 §5.3）——
 * 这是 docs/10「分母唯一依据」在 UI 上的落地，也是这个产品可信度的来源。
 */
export function formatFraction(m: number, n: number): string {
  return `${m} / ${n}`
}
