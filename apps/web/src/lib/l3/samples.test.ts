import { describe, expect, it } from 'vitest'

import type { Mention, RawResponseSummary } from '../types'

import { isPreviewTruncated, isValidSample, ownHit, pageLabel } from './samples'

const OWN = 34

const mention = (brandId: number, over: Partial<Mention> = {}): Mention => ({
  id: brandId * 100,
  brand_id: brandId,
  mentioned: true,
  mention_type: 'body',
  position_bucket: 'head',
  position_rank: 1,
  evidence_snippet: '……安踏的性价比……',
  // A7 起 MentionOut 多了这两个字段（高亮要用），后端一直会给，
  // 所以类型上是必填 —— 替身补齐即可
  first_offset: 0,
  matched_term: '安踏',
  ...over,
})

const sample = (over: Partial<RawResponseSummary> = {}): RawResponseSummary => ({
  id: 1,
  job_id: 1,
  platform: 'deepseek',
  prompt_text: '国产运动品牌推荐',
  text_preview: '这里是回答的前一百六十字',
  text_length: 12,
  screenshot_path: null,
  latency_ms: 1200,
  answer_status: 'ok',
  annotator_version: 'l1-2026.02',
  created_at: '2026-08-06T10:00:00Z',
  mentions: [mention(OWN)],
  ...over,
})

describe('ownHit', () => {
  it('正文命中带出场顺位与证据', () => {
    const hit = ownHit(sample(), OWN)
    expect(hit.kind).toBe('body')
    expect(hit.rank).toBe(1)
    expect(hit.snippet).toContain('安踏')
  })

  it('只按 brand_id 找本品，不看数组顺序', () => {
    // 竞品排在前面 —— 拿 mentions[0] 当本品会得到完全相反的结论
    const s = sample({
      mentions: [
        mention(99, { position_rank: 1 }),
        mention(OWN, { position_rank: 3 }),
      ],
    })
    expect(ownHit(s, OWN).rank).toBe(3)
  })

  it('citation_only 不是正文命中，也没有顺位', () => {
    const s = sample({
      mentions: [mention(OWN, { mention_type: 'citation_only', position_rank: null })],
    })
    const hit = ownHit(s, OWN)
    expect(hit.kind).toBe('citationOnly')
    expect(hit.rank).toBeNull()
  })

  it('标注过但没提及 → none', () => {
    const s = sample({
      mentions: [mention(OWN, { mentioned: false, mention_type: 'none', position_rank: null })],
    })
    expect(ownHit(s, OWN).kind).toBe('none')
  })

  it('标注过、本品干脆没有 mention 行 → 仍然是 none', () => {
    // annotate 会给每个被监测品牌都写一行（含未命中），所以标注过还缺行
    // 只能是竞品集变了；对本品而言结论仍是「这条没提到它」
    expect(ownHit(sample({ mentions: [] }), OWN).kind).toBe('none')
  })

  it('**没标注过 → unannotated，不是 none**', () => {
    // 这条是这个文件存在的理由：把「我们还没算」显示成「AI 没提你」
    // 是把降级态说成结论 —— 一个是我们的问题，一个是客户的问题
    const s = sample({ annotator_version: null, mentions: [] })
    expect(ownHit(s, OWN).kind).toBe('unannotated')
  })
})

describe('isValidSample', () => {
  it('只有 answer_status=ok 进分母', () => {
    expect(isValidSample(sample())).toBe(true)
    for (const st of ['empty', 'too_short', 'error', null]) {
      expect(isValidSample(sample({ answer_status: st }))).toBe(false)
    }
  })
})

describe('isPreviewTruncated 与 emoji', () => {
  it('预览含 emoji 时仍能判出被截断 —— 两边都按码点比', () => {
    // text_length 是 Postgres length()（码点）；JS 的 .length 是 UTF-16 单元。
    // 预览 5 个码点里有 2 个 emoji → JS .length 是 7，
    // 拿 6 > 7 比会把「被截断了」判成没截断，省略号就漏了
    expect(
      isPreviewTruncated(sample({ text_preview: '跑步🏃💡好', text_length: 6 })),
    ).toBe(true)
  })

  it('正好没截断时不误报', () => {
    expect(
      isPreviewTruncated(sample({ text_preview: '跑步🏃💡好', text_length: 5 })),
    ).toBe(false)
  })
})

describe('isPreviewTruncated', () => {
  it('总长大于预览长度才算截断', () => {
    expect(isPreviewTruncated(sample({ text_preview: 'abc', text_length: 3 }))).toBe(false)
    expect(isPreviewTruncated(sample({ text_preview: 'abc', text_length: 900 }))).toBe(true)
  })
})

describe('pageLabel', () => {
  it('给的是人话区间', () => {
    expect(pageLabel(0, 20, 35)).toBe('第 1–20 条 / 共 35 条')
    expect(pageLabel(20, 15, 35)).toBe('第 21–35 条 / 共 35 条')
  })

  it('没有数据时返回 null，让调用方走空态', () => {
    expect(pageLabel(0, 0, 0)).toBeNull()
  })
})
