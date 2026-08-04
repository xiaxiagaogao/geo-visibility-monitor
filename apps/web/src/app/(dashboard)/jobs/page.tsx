'use client'

import { useState } from 'react'

import {
  Badge,
  Button,
  EmptyState,
  FilterBar,
  PageHeader,
  Panel,
  SearchInput,
  Select,
  Table,
  tableStyles,
  Tabs,
} from '@/components/ui'
import { JOB_BATCHES, PROMPT_BY_ID, TOTALS } from '@/lib/fixtures'
import { formatRate, rate } from '@/lib/l3/rates'

/**
 * 抓取任务 —— 按日期分组，因为对持续监测来说「一天」就是天然的批次。
 *
 * 不做：未登录免费检测弹窗、多平台一键全选（无 Provider 时不假装可跑）。
 */
export default function JobsPage() {
  const [tab, setTab] = useState('all')

  return (
    <>
      <PageHeader
        crumbs={['监测台', '抓取任务']}
        title="抓取任务"
        subtitle="按日期分组 —— 对持续监测来说，「一天」就是天然的批次"
        actions={<Button primary>＋ 新建抓取</Button>}
      />

      <Tabs
        items={[
          { id: 'all', label: '全部', count: 35 },
          { id: 'pending', label: '待处理', count: 0 },
          { id: 'running', label: '进行中', count: 0 },
          { id: 'success', label: '成功', count: 35 },
          { id: 'failed', label: '失败', count: 0 },
        ]}
        active={tab}
        onChange={setTab}
      />

      <FilterBar>
        <SearchInput placeholder="搜索提问 / 关键词" />
        <Select label="平台" options={['全部平台', 'DeepSeek']} />
        <Button>重置</Button>
        <Button>刷新</Button>
      </FilterBar>

      {JOB_BATCHES.map((batch) => {
        const totalSamples = batch.rows.reduce((acc, r) => acc + r.samples, 0)
        const totalHits = batch.rows.reduce((acc, r) => acc + r.m, 0)

        return (
          <div key={batch.date} style={batch.dimmed ? { opacity: 0.55 } : undefined}>
            <Panel
              title={`${batch.date} · ${batch.label}`}
              subtitle={batch.note}
              right={
                batch.rows.length > 0 ? (
                  <span className="mono" style={{ fontSize: 'var(--fs-sm)', color: 'var(--muted)' }}>
                    本品提及率{' '}
                    <span style={{ color: 'var(--accent)', fontWeight: 600 }}>
                      {formatRate(rate(totalHits, totalSamples))}
                    </span>{' '}
                    · {totalHits}/{totalSamples}
                  </span>
                ) : undefined
              }
            >
              {batch.rows.length === 0 ? (
                <EmptyState>
                  这一批的明细接上 <code>GET /v1/crawl-jobs</code> 后展开。
                </EmptyState>
              ) : (
                <Table>
                  <thead>
                    <tr>
                      <th style={{ width: '42%' }}>提问</th>
                      <th>类型</th>
                      <th>样本</th>
                      <th>状态</th>
                      <th>本品</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {batch.rows.map((row) => {
                      const prompt = PROMPT_BY_ID.get(row.promptId)
                      const r = rate(row.m, row.samples)
                      const zero = r === 0
                      const full = r === 1

                      return (
                        <tr key={row.promptId}>
                          <td>{prompt?.text ?? `#${row.promptId}`}</td>
                          <td>
                            <Badge>{prompt?.category ?? '—'}</Badge>
                          </td>
                          <td className="mono">{row.samples}</td>
                          <td>
                            <Badge tone={row.status === 'success' ? 'ok' : 'bad'}>
                              {row.status === 'success' ? '成功' : '失败'}
                            </Badge>
                          </td>
                          <td
                            className="mono"
                            style={{
                              color: zero
                                ? 'var(--bad)'
                                : full
                                  ? 'var(--seq-3)'
                                  : undefined,
                            }}
                          >
                            {row.m}/{row.samples}
                          </td>
                          <td>
                            <a className={tableStyles.rowLink} href={`/responses/?p=${row.promptId}&rid=29`}>
                              查看 ›
                            </a>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </Table>
              )}
            </Panel>
          </div>
        )
      })}

      <p style={{ fontSize: 'var(--fs-sm)', color: 'var(--muted)', marginTop: 'var(--sp-4)' }}>
        合计 {TOTALS.nValid} 条有效样本。发起新抓取是写操作，必须带 <code>X-API-Key</code> 请求头 ——
        Cookie 只对 GET/HEAD/OPTIONS 有效，这条 CSRF 红线有测试守着。
      </p>
    </>
  )
}
