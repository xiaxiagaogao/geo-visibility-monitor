import { Badge, EmptyState, Panel, PanelNote, Table, ui } from '@/components/ui'
import { PROMPT_BY_ID } from '@/lib/fixtures'
import { formatRate, rate } from '@/lib/l3/rates'
import { brandName, gapList, promptText } from '@/lib/selectors'

const PRIORITY_LABEL = { high: '高', mid: '中', low: '低' } as const
const PRIORITY_TONE = { high: 'danger', mid: 'warning', low: 'neutral' } as const

/**
 * 覆盖缺口 —— 本品缺席或明显落后、竞品在场的提问清单。
 *
 * 这是整个看板唯一数据完全齐备、且输出可直接执行的页面：
 * 结果是一张「该去哪些提问下补内容」的清单，可以直接交给推流团队。
 */
export default function GapsPage() {
  const gaps = gapList()
  const absent = gaps.filter((g) => g.tier === 'absent')
  const trailing = gaps.filter((g) => g.tier === 'trailing')

  return (
    <>
      <Panel
        title="缺口清单"
        subtitle="失分量 = Σ max(0, 竞品命中数 − 本品命中数)，读作「竞品合计比本品多拿了多少次提及」"
        right={
          <div style={{ display: 'flex', gap: 8 }}>
            <Badge tone="danger">{absent.length} 条完全缺席</Badge>
            <Badge tone="warning">{trailing.length} 条明显落后</Badge>
          </div>
        }
      >
        {gaps.length === 0 ? (
          <EmptyState>
            当前筛选范围内没有缺口 —— 本品在每条提问下都不落后于竞品。
          </EmptyState>
        ) : (
          <Table>
            <thead>
              <tr>
                <th style={{ width: '30%' }}>缺口提问</th>
                <th>类型</th>
                <th>缺口档</th>
                <th>本品</th>
                <th style={{ width: '28%' }}>在场竞品</th>
                <th style={{ textAlign: 'right' }}>失分量</th>
                <th style={{ textAlign: 'right' }}>优先级</th>
              </tr>
            </thead>
            <tbody>
              {gaps.map((g) => {
                const ownRate = rate(g.ownM, g.n)
                return (
                  <tr key={g.promptId}>
                    <td>{promptText(g.promptId)}</td>
                    <td>
                      <Badge>{PROMPT_BY_ID.get(g.promptId)?.category ?? '—'}</Badge>
                    </td>
                    <td>
                      <Badge tone={g.tier === 'absent' ? 'danger' : 'warning'}>
                        {g.tier === 'absent' ? '完全缺席' : '明显落后'}
                      </Badge>
                    </td>
                    <td
                      className={ui.numeric}
                      style={{ color: g.ownM === 0 ? 'var(--danger)' : undefined }}
                    >
                      {formatRate(ownRate)}
                      <span style={{ color: 'var(--text-tertiary)', marginLeft: 6 }}>
                        {g.ownM}/{g.n}
                      </span>
                    </td>
                    <td style={{ fontSize: 'var(--fs-xs)', color: 'var(--text-secondary)' }}>
                      {g.competitorsPresent
                        .map((c) => `${brandName(c.brandId)} ${c.m}/${g.n}`)
                        .join(' · ')}
                    </td>
                    <td className={ui.numeric} style={{ textAlign: 'right', fontWeight: 600 }}>
                      {g.score}
                    </td>
                    <td style={{ textAlign: 'right' }}>
                      <Badge tone={PRIORITY_TONE[g.priority]}>{PRIORITY_LABEL[g.priority]}</Badge>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </Table>
        )}
      </Panel>

      <PanelNote>
        「明显落后」这一档是我们对竞品设计的扩展 —— 它只定义了完全缺席。
        但 1/3 对 3/3 同样是丢单，只做 0 分那一档会漏掉一半的可执行信息。
        判定阈值是「本品命中率 &lt; 最高竞品的一半」，跑过一轮真实数据后可回调。
      </PanelNote>
    </>
  )
}
