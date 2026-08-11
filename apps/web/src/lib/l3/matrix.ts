/**
 * 命中矩阵 —— 行是提问、列是品牌、格是「这条提问下这个品牌被提到几次」。
 *
 * 这个文件干的其实只有一件事：**把两份数据 join 对**。而这个 join 有三处
 * 一错就静默出错、界面上完全看不出来的地方，所以它值得单独成层、单独测：
 *
 *   1. 行源必须是 run 快照的 `prompts`，**不是 counts 的 series**
 *   2. 列必须按 `brand_id` 关联，**不许按数组下标**（API.md §4.2 第 3 条）
 *   3. `n = 0`（不可算）和 `m = 0`（真的是 0）是两个格，**不是同一个格**
 *
 * 纯函数，不碰 fetch 与 React。
 */
import type { CountsBucket, RunCompetitor, RunPrompt } from '../types'

import type { GapInput } from './gaps'
import { matrixLevel, rate, type MatrixLevel } from './rates'

/**
 * 一个格的形态。
 *
 * `hit` / `zero` / `zeroOwn` 是设计稿定的三态（原第四态是「命中 · 有顺位」，
 * 格里加一个 `#N` 副标 —— 那需要**顺位分布**，而 counts 只给得出
 * `m_first` 这一个计数，反推名次就是编数据，所以现在只显示 m/n，
 * 见 API.md §9 最后一行）。
 *
 * `na` 是第四个、也是最容易被吞掉的一个：这条提问这次**一条有效样本都没有**。
 * 它必须和 `zero` 分开 —— 「算不出」不是「真的是 0」，这是 `rate()` 返回
 * `null` 与 `0` 的同一条纪律。色阶函数 `matrixLevel()` 把两者都归到
 * `'zero'`，因为它只管配色；语义的分岔在这里做。
 */
export type MatrixCellKind = 'hit' | 'zero' | 'zeroOwn' | 'na'

export interface MatrixCell {
  brandId: number
  kind: MatrixCellKind
  /** 色阶档位。只有 `kind === 'hit'` 时有意义 */
  level: MatrixLevel
  m: number
  n: number
  rate: number | null
}

export interface MatrixRow {
  promptId: number
  /** 取自 run 快照的 `prompt_text` —— 提问词后来改了名也不会改写这次的历史 */
  promptText: string
  /** 这条提问在这次 run 里的有效样本数，全行公共分母 */
  n: number
  ownM: number
  ownRate: number | null
  /** `[本品, ...竞品]`，竞品按 run 快照的顺序 */
  cells: MatrixCell[]
}

/**
 * 一个格。
 *
 * `own` 只影响挂零那一态：本品缺席是这个产品的核心结论，
 * 不能和「某个竞品没出现」用同一个样式。
 */
export function buildCell(brandId: number, m: number, n: number, own: boolean): MatrixCell {
  const r = rate(m, n)
  const kind: MatrixCellKind =
    r === null ? 'na' : r === 0 ? (own ? 'zeroOwn' : 'zero') : 'hit'
  return { brandId, kind, level: matrixLevel(r), m, n, rate: r }
}

/**
 * 组装矩阵。
 *
 * **行源是 `prompts` 快照，不是 `series`。** counts 的 series 只包含
 * 真的有 response 的提问 —— 拿它当行源，这次跑空的提问会**静默消失**：
 * 用户看到 8 行，以为这次只跑了 8 条提问，而实际是 10 条、有 2 条全挂。
 * 那不是少画了两行，那是在隐瞒失败。用快照当行源，它们仍然占一行显示 `—`。
 */
export function buildMatrix(params: {
  ownBrandId: number
  /** run 快照的提问集，决定行与行序 */
  prompts: RunPrompt[]
  /** run 快照的竞品集，决定列与列序 */
  competitors: RunCompetitor[]
  /** `group_by=prompt` 的 series */
  series: CountsBucket[]
}): MatrixRow[] {
  const { ownBrandId, prompts, competitors, series } = params

  // series[].key 是 **prompt_id 的字符串**，不是提问文案（API.md §4.2 第 2 条）
  const byPromptId = new Map(series.map((b) => [b.key, b]))

  return prompts.map((p) => {
    const bucket = byPromptId.get(String(p.prompt_id))
    const n = bucket?.denominator.n_valid ?? 0
    const ownM = bucket?.brand.m_mentioned ?? 0

    // 竞品按 brand_id 关联。**数组下标不保证顺序**，而下标错位的矩阵
    // 每一格都有值、每一格都是错的 —— 界面上完全看不出来。
    const compM = new Map((bucket?.competitors ?? []).map((c) => [c.brand_id, c.m_mentioned]))

    return {
      promptId: p.prompt_id,
      promptText: p.prompt_text,
      n,
      ownM,
      ownRate: rate(ownM, n),
      cells: [
        buildCell(ownBrandId, ownM, n, true),
        ...competitors.map((c) =>
          buildCell(c.competitor_brand_id, compM.get(c.competitor_brand_id) ?? 0, n, false),
        ),
      ],
    }
  })
}

/**
 * 缺口清单的入参 —— 从矩阵行导出，**不重新 join 一次**。
 *
 * 两处各 join 一次的话，矩阵和缺口清单迟早会对不上（一处改了关联方式、
 * 另一处没改），而它们说的本来就是同一批数。共用一个 join 让这种分叉
 * 在结构上不可能发生。
 *
 * `n = 0` 的行直接丢掉：`classifyGap` 对它返回 `null`（分母为 0 判不了缺口），
 * 留着只是让下游多走一圈。
 */
export function gapInputsFromMatrix(rows: MatrixRow[]): GapInput[] {
  return rows
    .filter((r) => r.n > 0)
    .map((r) => ({
      promptId: r.promptId,
      n: r.n,
      ownM: r.ownM,
      // 第 0 格是本品，缺口只看竞品
      competitors: r.cells.slice(1).map((c) => ({ brandId: c.brandId, m: c.m })),
    }))
}
