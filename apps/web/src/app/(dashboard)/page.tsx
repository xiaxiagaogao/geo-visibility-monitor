import { EmphasisBars } from '@/components/charts/EmphasisBars'
import { Badge, CountCard, Meter, MeterGrid, PageHeader, Panel } from '@/components/ui'
import { TOTALS } from '@/lib/fixtures'
import {
  brandComparison,
  fullHitPromptCount,
  ownRateByPrompt,
  sovDenominator,
  zeroHitPromptCount,
} from '@/lib/selectors'

/**
 * 总览。
 *
 * 这一页只有一个任务：**让 60% 这个数字当场自我解释**（docs/27 §6.1）。
 * 60% 是「5 条满分 + 2 条挂零」平均出来的，不是稳定表现 ——
 * 所以四个 meter 底下必须紧跟逐提问分布，不能让大数字单独站着。
 *
 * 明确不做：营销大字 slogan 首屏（竞品工作台那一套，docs/27 §12）。
 */
export default function OverviewPage() {
  const perPrompt = ownRateByPrompt()
  const brands = brandComparison()
  const zeroCount = zeroHitPromptCount()
  const fullCount = fullHitPromptCount()
  const sovDen = sovDenominator()

  return (
    <>
      <PageHeader
        crumbs={['监测台', '总览']}
        title="总览"
        subtitle="分母 = answer_status ok · 已排除假数据 · 口径来自 /v1/config/metrics"
      />

      <MeterGrid>
        <CountCard
          label="有效样本"
          info="分母定义：answer_status = ok，已排除 fake 来源"
          value={TOTALS.nValid}
          note={`${TOTALS.nValid} / ${TOTALS.nTotalResponses} 全部有效`}
        />
        <Meter
          label="本品提及率"
          info="本品被提及的样本数 ÷ 有效样本数"
          m={TOTALS.brand.mMentioned}
          n={TOTALS.nValid}
          tone="accent"
        />
        <Meter
          label="头部位置占比"
          info="首次出现在回答头部的次数 ÷ 被提及次数"
          m={TOTALS.brand.mHead}
          n={TOTALS.brand.mMentioned}
          tone="dim"
        />
        <Meter
          label="声量份额 SoV"
          info="本品命中数 ÷（本品 + 全部竞品命中数）"
          m={TOTALS.brand.mMentioned}
          n={sovDen}
          tone="dim"
        />
        <CountCard
          label="零命中提问"
          info="本品一次都没有被提到的提问条数"
          value={zeroCount}
          note={`共 ${perPrompt.length} 条提问`}
          tone={zeroCount > 0 ? 'bad' : 'dim'}
        />
      </MeterGrid>

      <Panel
        title="60% 是两极平均出来的，不是稳定表现"
        subtitle={`${perPrompt.length} 条提问里 ${fullCount} 条满分、${zeroCount} 条挂零 —— 到「回答明细」点任意格子可下钻到证据`}
        right={<Badge tone="bad">{zeroCount} 条挂零</Badge>}
      >
        <EmphasisBars data={perPrompt} maxRate={1} />
      </Panel>

      <Panel
        title="品牌提及对比"
        subtitle="emphasis：本品强调色，竞品统一灰 —— 8 个品牌不需要 8 种颜色"
        flush
      >
        <EmphasisBars data={brands} maxRate={1} />
      </Panel>
    </>
  )
}
