/**
 * 品牌配置的派生逻辑（A2）——别名与竞品的编辑。
 *
 * 这一层守的是同一件事：**`PUT /aliases` 与 `PUT /competitors` 是整体替换**
 * （API.md §6），不是增量。提交的列表就是提交后的全部，漏掉的会被删掉。
 *
 * 所以编辑器必须始终拿着**全量**。这不是 UI 细节：一个「加一个别名」的按钮
 * 如果只 PUT 新增那一个，会把其余别名全删掉 —— 而接口返回 200，
 * 页面刷新后看起来「只是没保存上」，没人会想到是自己删的。
 *
 * 纯函数，不碰 fetch 与 React。
 */

/**
 * 别名归一化 —— **照抄后端 `services/brands._normalize_aliases`**：
 * 去首尾空白 · 丢空串 · 按 casefold 去重 · **保留首次出现时的大小写** · 保持顺序。
 *
 * 前端跟着做一遍不是重复劳动，是为了让编辑器里看到的就是保存后的结果。
 * 两边口径必须一致：这边多留一条、后端吃掉了，用户会以为保存失败。
 *
 * 权威仍在后端 —— 这里只是让所见即所得，**不做后端没有的额外清洗**
 * （比如全角转半角），那种「贴心」会让前端显示的和库里存的对不上。
 */
export function normalizeAliases(aliases: string[]): string[] {
  const seen = new Set<string>()
  const out: string[] = []
  for (const raw of aliases) {
    const s = (raw ?? '').trim()
    if (!s) continue
    // casefold 在 JS 里最接近的是 toLowerCase()；两边对「Nike / nike / NIKE」
    // 的判断一致，这是实际会遇到的形态
    const key = s.toLowerCase()
    if (seen.has(key)) continue
    seen.add(key)
    out.push(s)
  }
  return out
}

/**
 * 文本框 → 别名数组。**一行一个。**
 *
 * 用多行文本框而不是「chip + 加号」，正是因为接口是整体替换：
 * 文本框里显示的就是提交后的全部，语义一眼可见。
 * chip 式编辑器看起来像增量操作，和接口语义相反。
 */
export function parseAliasLines(text: string): string[] {
  return normalizeAliases(text.split('\n'))
}

/** 别名数组 → 文本框内容 */
export function formatAliasLines(aliases: string[]): string {
  return aliases.join('\n')
}

/**
 * 竞品集的清洗 —— **照抄后端 `replace_competitors` 的三条**：
 * 不能是自己 · 去重 · 必须是已存在的品牌。
 *
 * 前端先挡一道不是为了替代后端校验（那是安全边界），
 * 是为了别让用户点了保存才收到一个 400。
 */
export function sanitizeCompetitorIds(
  ids: number[],
  selfId: number,
  knownIds: Iterable<number>,
): number[] {
  const known = new Set(knownIds)
  const seen = new Set<number>()
  const out: number[] = []
  for (const id of ids) {
    // 自己不能当自己的竞品 —— 后端是 400，这里直接不给选中
    if (id === selfId) continue
    if (seen.has(id)) continue
    if (!known.has(id)) continue
    seen.add(id)
    out.push(id)
  }
  return out
}

/** 勾选 / 取消一个竞品，返回新数组（不改原数组） */
export function toggleCompetitor(ids: number[], id: number): number[] {
  return ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id]
}

/**
 * 两个列表是不是一样（顺序敏感）—— 用来判断「有没有改动」。
 *
 * **顺序敏感是刻意的**：竞品的列顺序是矩阵列顺序的唯一依据
 * （`Brand.competitor_ids`，见 types.ts），调了顺序就是真的改了东西，
 * 不该被当成「没变化」而禁用保存按钮。
 */
export function sameList<T>(a: readonly T[], b: readonly T[]): boolean {
  return a.length === b.length && a.every((v, i) => v === b[i])
}
