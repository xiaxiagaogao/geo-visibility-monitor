import { describe, expect, it } from 'vitest'

import { MATRIX, MATRIX_COLUMNS, OWN_BRAND_ID, PROMPTS, SAMPLE_RESPONSE, TOTALS } from './fixtures'
import { rate } from './l3/rates'

/**
 * 这些不是「测试数据结构」，是**核对真实数字**。
 * 矩阵是逐格从设计稿抄下来的，一旦手抖，总览的 60.0% 和矩阵就会对不上 ——
 * 这几条断言就是为了让那种错当场炸掉，而不是等上线后被人发现看板在骗人。
 * 基准见 API.md §10（快照日期 2026-08-06，重抓后会变）。
 */
describe('安踏监测集固定数据自洽性', () => {
  it('每行样本数求和 = 35 条有效样本', () => {
    const n = MATRIX.reduce((acc, r) => acc + r.n, 0)
    expect(n).toBe(TOTALS.nValid)
  })

  it('本品逐行命中求和 = 21', () => {
    const own = MATRIX.reduce((acc, r) => {
      const cell = r.cells.find((c) => c.brandId === OWN_BRAND_ID)
      return acc + (cell?.m ?? 0)
    }, 0)
    expect(own).toBe(TOTALS.brand.mMentioned)
  })

  it('本品提及率 = 60.0%', () => {
    expect(rate(TOTALS.brand.mMentioned, TOTALS.nValid)).toBeCloseTo(0.6, 10)
  })

  it('每个竞品的逐行命中求和都对得上总计', () => {
    for (const comp of TOTALS.competitors) {
      const summed = MATRIX.reduce((acc, r) => {
        const cell = r.cells.find((c) => c.brandId === comp.brandId)
        return acc + (cell?.m ?? 0)
      }, 0)
      expect(summed, `brand ${comp.brandId}`).toBe(comp.mMentioned)
    }
  })

  it('八个品牌命中总数 137 —— 这是 API.md §10 记的基准', () => {
    const total = TOTALS.competitors.reduce((acc, c) => acc + c.mMentioned, TOTALS.brand.mMentioned)
    expect(total).toBe(137)
  })

  it('没有哪一格的命中数超过该行样本数', () => {
    for (const r of MATRIX) {
      for (const cell of r.cells) {
        expect(cell.m ?? 0, `prompt ${r.promptId} / brand ${cell.brandId}`).toBeLessThanOrEqual(r.n)
      }
    }
  })

  it('每行都有全部 8 列，且提问都能关联到 prompt', () => {
    const ids = new Set(PROMPTS.map((p) => p.id))
    for (const r of MATRIX) {
      expect(r.cells).toHaveLength(MATRIX_COLUMNS.length)
      expect(ids.has(r.promptId), `prompt ${r.promptId}`).toBe(true)
    }
  })

  it('样例样本的 position_rank 必须全是 null —— 库里就是这样，填上就是编数据', () => {
    // annotate.py:154 每条 mention 都硬编码 position_rank=None / sentiment=None。
    // 一旦这里填了 #1 #2 #3，「首位提及率」的降级态就自相矛盾了。
    // 后端按 offset 升序回填之后，连同这条断言一起改。
    for (const m of SAMPLE_RESPONSE.mentions) {
      expect(m.position_rank, `brand ${m.brand_id}`).toBeNull()
    }
  })

  it('双峰结论仍在：5 条满分、2 条本品挂零', () => {
    const ownRates = MATRIX.map((r) => {
      const m = r.cells.find((c) => c.brandId === OWN_BRAND_ID)?.m ?? 0
      return m / r.n
    })
    expect(ownRates.filter((x) => x === 1)).toHaveLength(5)
    expect(ownRates.filter((x) => x === 0)).toHaveLength(2)
  })
})
