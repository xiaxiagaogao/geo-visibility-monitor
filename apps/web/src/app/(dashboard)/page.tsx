import Link from 'next/link'

import { EmphasisBars } from '@/components/charts/EmphasisBars'
import { Badge, KpiCount, KpiDegraded, KpiGrid, KpiRate, Panel, PanelNote, Table, ui } from '@/components/ui'
import { BATCHES, TOTALS } from '@/lib/fixtures'
import { formatRate, rate } from '@/lib/l3/rates'
import {
  brandComparison,
  brandName,
  fullHitPromptCount,
  gapList,
  ownRateByPrompt,
  promptText,
  zeroHitPromptCount,
} from '@/lib/selectors'

import styles from './overview.module.css'

/**
 * 总览。
 *
 * 这一页只有一个任务：**让 60% 这个数字当场自我解释**（docs/27 §6.1）。
 * 60% 是「5 条满分 + 2 条挂零」平均出来的，不是稳定表现 ——
 * 所以 KPI 底下必须紧跟逐提问分布，不能让大数字单独站着。
 *
 * 明确不做：GeoMonitor 工作台那种营销大字首屏（docs/27 §12）。
 */
export default function OverviewPage() {
  const perPrompt = ownRateByPrompt()
  const brands = brandComparison()
  const gaps = gapList()
  const zeroCount = zeroHitPromptCount()
  const fullCount = fullHitPromptCount()

  return (
    <>
      <KpiGrid>
        <KpiCount
          label="有效样本"
          info="分母定义：answer_status = ok，已排除 fake 来源"
          value={TOTALS.nValid}
          note={`${TOTALS.nValid} / ${TOTALS.nTotalResponses} 全部有效`}
        />
        <KpiRate
          label="本品提及率"
          info="本品被提及的样本数 ÷ 有效样本数"
          m={TOTALS.brand.mMentioned}
          n={TOTALS.nValid}
        />
        {/* 后端还没落库 position_rank —— 走降级态而不是显示 0%（docs/29 §5.3） */}
        <KpiDegraded
          label="首位提及率"
          info="本品出场顺位为 1 的样本数 ÷ 本品被提及样本数。注意是「第一个被提到」，不是「被推荐第一」"
          reason="暂无排名数据"
          note="待后端落库 position_rank"
        />
        <KpiCount
          label="覆盖缺口"
          info="本品缺席或明显落后、且竞品在场的提问数"
          value={gaps.length}
          note={`${gaps.filter((g) => g.tier === 'absent').length} 条完全缺席 · ${gaps.filter((g) => g.tier === 'trailing').length} 条明显落后`}
          alert={gaps.length > 0}
        />
      </KpiGrid>

      <Panel
        title="60% 是两极平均出来的，不是稳定表现"
        subtitle={`${perPrompt.length} 条提问里 ${fullCount} 条满分、${zeroCount} 条挂零 —— 平均值把这个结构盖掉了`}
        right={<Badge tone="danger">{zeroCount} 条挂零</Badge>}
      >
        <EmphasisBars data={perPrompt} />
      </Panel>

      <div className={styles.split}>
        <Panel
          title="覆盖缺口 · 优先处理"
          subtitle="按失分量排序 —— 竞品比本品多拿了多少次提及"
          right={
            <Link href="/gaps/" className={ui.rowLink}>
              查看全部 {gaps.length} 条 ›
            </Link>
          }
        >
          <Table>
            <thead>
              <tr>
                <th>缺口提问</th>
                <th>本品</th>
                <th>在场竞品</th>
                <th style={{ textAlign: 'right' }}>失分量</th>
              </tr>
            </thead>
            <tbody>
              {gaps.slice(0, 3).map((g) => (
                <tr key={g.promptId}>
                  <td>
                    <div>{promptText(g.promptId)}</div>
                    <div style={{ marginTop: 3 }}>
                      <Badge tone={g.tier === 'absent' ? 'danger' : 'warning'}>
                        {g.tier === 'absent' ? '完全缺席' : '明显落后'}
                      </Badge>
                    </div>
                  </td>
                  <td className={ui.numeric} style={{ color: g.ownM === 0 ? 'var(--danger)' : undefined }}>
                    {g.ownM}/{g.n}
                  </td>
                  <td style={{ color: 'var(--text-secondary)', fontSize: 'var(--fs-xs)' }}>
                    {g.competitorsPresent
                      .slice(0, 3)
                      .map((c) => `${brandName(c.brandId)} ${c.m}/${g.n}`)
                      .join(' · ')}
                  </td>
                  <td className={ui.numeric} style={{ textAlign: 'right', fontWeight: 600 }}>
                    {g.score}
                  </td>
                </tr>
              ))}
            </tbody>
          </Table>
        </Panel>

        <Panel title="最近采集批次" subtitle="批次 = 采集日期">
          <Table>
            <thead>
              <tr>
                <th>日期</th>
                <th>样本</th>
                <th>本品提及率</th>
                <th>状态</th>
              </tr>
            </thead>
            <tbody>
              {BATCHES.map((b) => {
                const samples = b.rows.reduce((acc, r) => acc + r.samples, 0)
                const hits = b.rows.reduce((acc, r) => acc + r.m, 0)
                return (
                  <tr key={b.date}>
                    <td>
                      <div className={ui.numeric}>{b.date}</div>
                      <div style={{ fontSize: 'var(--fs-xs)', color: 'var(--text-tertiary)' }}>
                        {b.label}
                      </div>
                    </td>
                    <td className={ui.numeric}>{b.expanded ? samples : '13'}</td>
                    <td className={ui.numeric}>
                      {b.expanded ? formatRate(rate(hits, samples)) : '0.0%'}
                    </td>
                    <td>
                      <Badge tone="ok" dot>
                        成功
                      </Badge>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </Table>
        </Panel>
      </div>

      <Panel
        title="品牌提及对比"
        subtitle="emphasis：本品强调色，竞品统一灰 —— 8 个品牌不需要 8 种颜色"
      >
        <EmphasisBars data={brands} />
      </Panel>

      <PanelNote>
        读法：国产 / 性价比 / 篮球类提问下，本品与国产品牌成片命中、国际品牌成片空白；
        专业跑鞋 / 训练类正好反过来。这个互补结构就是这套监测集给出的第一个结论 ——
        也是「60%」这个数字背后的真相。每条提问只跑 3–5 次采样，比率的置信区间很宽，
        请按数量级读而不是按小数点读。
      </PanelNote>
    </>
  )
}
