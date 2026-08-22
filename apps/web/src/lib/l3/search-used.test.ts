import { describe, expect, it } from 'vitest'

import { citationState, searchUsedLabel } from './search-used'

/**
 * 联网标注是**三态**（P2-37，`API.md` §7）。
 *
 * 这份测试守的就是一件事：**`null` 不是 `false`。**
 *
 * `null` = 我们不知道（P2-37 上线前的全部样本、别的平台、解析失败）；
 * `false` = **确认**这次没联网。把前者显示成后者，就是在界面上凭空断言
 * 一件我们没测过的事 —— 而库里现在有 55 条 `null` 的历史样本正等着被这样误读。
 */
describe('searchUsedLabel', () => {
  it('true 是「联网了」', () => {
    expect(searchUsedLabel(true).text).toBe('已联网')
    expect(searchUsedLabel(true).tone).toBe('ok')
  })

  it('false 是「确认没联网」，而且它是结论不是缺陷', () => {
    const s = searchUsedLabel(false)
    expect(s.text).toBe('未联网')
    // **不能用 danger** —— §4.0.1 拍板「无搜索输出是结果，不是废样本」，
    // 标成红色等于在界面上说这条样本有问题
    expect(s.tone).not.toBe('danger')
  })

  it('null 必须自成一档，文案里不能出现「未联网」', () => {
    const s = searchUsedLabel(null)
    expect(s.text).not.toContain('未联网')
    expect(s.degraded).toBe(true)
  })

  it('只有 null 是降级态', () => {
    expect(searchUsedLabel(true).degraded).toBe(false)
    expect(searchUsedLabel(false).degraded).toBe(false)
  })
})

/**
 * 「这条样本为什么没有引用」有四种完全不同的答案，
 * 界面上必须分得开 —— 否则用户会拿「没引用」当成「AI 没参考任何来源」。
 */
describe('citationState', () => {
  it('有引用就是有引用', () => {
    expect(citationState(1, true)).toBe('has')
    expect(citationState(3, null)).toBe('has')
  })

  it('确认没联网 → 没有引用是应然结果', () => {
    expect(citationState(0, false)).toBe('none-no-search')
  })

  it('不知道有没有联网 → 是降级，不是结论', () => {
    expect(citationState(0, null)).toBe('unknown')
  })

  it('联网了却一条引用都没抽到 → 这是异常，要显眼', () => {
    // 说明流解析出了问题（或平台改了结构），不能和「没联网」混为一谈 ——
    // 后者是正常的，前者是我们的 bug
    expect(citationState(0, true)).toBe('none-despite-search')
  })
})
