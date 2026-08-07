'use client'

import { useRouter } from 'next/navigation'
import { useState } from 'react'

import { HitMatrix } from '@/components/charts/HitMatrix'
import {
  Badge,
  EmptyState,
  KpiCount,
  KpiDegraded,
  KpiGrid,
  KpiRate,
  Panel,
  PanelNote,
  Table,
  Tabs,
  ui,
} from '@/components/ui'
import { BATCHES, MATRIX, MATRIX_COLUMNS, PROMPT_BY_ID, SAMPLE_RESPONSE, TOTALS } from '@/lib/fixtures'
import { formatRate, rate } from '@/lib/l3/rates'
import { gapList, promptText } from '@/lib/selectors'

/**
 * 采集批次 —— 批次就是**一天**。
 * 后端没有「批次 / 检测」这个实体（API.md §9），只能按 created_at 日期分组当批次。
 * 对持续监测来说「一天」也确实是天然的批次，且零后端改动。
 */
export function BatchesView() {
  const router = useRouter()
  const [tab, setTab] = useState('matrix')

  const batch = BATCHES[0]
  const samples = batch.rows.reduce((acc, r) => acc + r.samples, 0)
  const hits = batch.rows.reduce((acc, r) => acc + r.m, 0)
  const gaps = gapList()

  const openEvidence = (promptId: number) =>
    router.push(`/responses/?p=${promptId}&rid=${SAMPLE_RESPONSE.id}`)

  return (
    <>
      <Panel>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <strong style={{ fontSize: 'var(--fs-h2)' }}>
            {batch.date} · {batch.label}
          </strong>
          <Badge tone="ok" dot>
            全部成功
          </Badge>
          <span style={{ flex: 1 }} />
          <span style={{ fontSize: 'var(--fs-xs)', color: 'var(--text-tertiary)' }}>
            {batch.note}
          </span>
        </div>
      </Panel>

      <KpiGrid>
        <KpiCount
          label="有效样本"
          info="分母定义：answer_status = ok，已排除 fake 来源"
          value={samples}
          note={`${samples} / ${samples} 全部有效`}
        />
        <KpiRate label="本品提及率" info="本品被提及的样本数 ÷ 有效样本数" m={hits} n={samples} />
        <KpiDegraded
          label="首位提及率"
          info="本品出场顺位为 1 的样本数 ÷ 本品被提及样本数"
          reason="暂无排名数据"
          note="待前端接入 position_rank"
        />
        <KpiCount
          label="覆盖缺口"
          info="本品缺席或明显落后、且竞品在场的提问数"
          value={gaps.length}
          note={`本批 ${batch.rows.length} 条提问中`}
          alert={gaps.length > 0}
        />
      </KpiGrid>

      <Tabs
        items={[
          { id: 'matrix', label: '命中矩阵' },
          { id: 'citations', label: '引用分析' },
          { id: 'samples', label: '样本列表', count: samples },
        ]}
        active={tab}
        onChange={setTab}
      />

      {tab === 'matrix' ? (
        <>
          <Panel
            title="提问 × 品牌 命中矩阵"
            subtitle="格内为 命中 / 样本；虚线 = 未提及；红色虚线 = 本品挂零。点任意实心格下钻到证据"
          >
            <HitMatrix rows={MATRIX} columns={MATRIX_COLUMNS} onPick={openEvidence} />
          </Panel>
          <PanelNote>
            排名可能没有序号 ——「已提及·未排名」必须和「未提及」视觉区分，绝不伪造名次。
            接上 <code>position_rank</code> 之前，格内一个 <code>#</code> 都不显示。
            每条提问 3–5 次采样，比率的置信区间很宽，请按数量级读。
          </PanelNote>
        </>
      ) : null}

      {tab === 'citations' ? (
        <Panel title="本批引用来源">
          <EmptyState>
            采集样本时未开启联网搜索，模型回答里不含引用来源。
            <br />
            这不是采集故障 —— 要有数据得开联网后重采，而重采会破坏与现有基线的可比性。
          </EmptyState>
        </Panel>
      ) : null}

      {tab === 'samples' ? (
        <Panel title="样本列表" subtitle="逐条提问的采样结果，可下钻到原始回答">
          <Table>
            <thead>
              <tr>
                <th style={{ width: '40%' }}>提问</th>
                <th>类型</th>
                <th>样本</th>
                <th>状态</th>
                <th>本品</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {batch.rows.map((row) => {
                const r = rate(row.m, row.samples)
                const zero = r === 0
                const full = r === 1
                return (
                  <tr key={row.promptId}>
                    <td>{promptText(row.promptId)}</td>
                    <td>
                      <Badge>{PROMPT_BY_ID.get(row.promptId)?.category ?? '—'}</Badge>
                    </td>
                    <td className={ui.numeric}>{row.samples}</td>
                    <td>
                      <Badge tone="ok" dot>
                        成功
                      </Badge>
                    </td>
                    <td
                      className={ui.numeric}
                      style={{
                        color: zero ? 'var(--danger)' : full ? 'var(--accent)' : undefined,
                        fontWeight: zero || full ? 600 : undefined,
                      }}
                    >
                      {formatRate(r)}
                      <span style={{ color: 'var(--text-tertiary)', marginLeft: 6 }}>
                        {row.m}/{row.samples}
                      </span>
                    </td>
                    <td style={{ textAlign: 'right' }}>
                      <button className={ui.rowLink} onClick={() => openEvidence(row.promptId)}>
                        查看 ›
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </Table>
        </Panel>
      ) : null}

      <Panel title="更早的批次">
        <Table>
          <thead>
            <tr>
              <th>日期</th>
              <th>监测集</th>
              <th>说明</th>
            </tr>
          </thead>
          <tbody>
            {BATCHES.slice(1).map((b) => (
              <tr key={b.date}>
                <td className={ui.numeric}>{b.date}</td>
                <td>{b.label}</td>
                <td style={{ color: 'var(--text-tertiary)', fontSize: 'var(--fs-xs)' }}>{b.note}</td>
              </tr>
            ))}
          </tbody>
        </Table>
      </Panel>

      <span className="srOnly">当前合计 {TOTALS.nValid} 条有效样本</span>
    </>
  )
}
