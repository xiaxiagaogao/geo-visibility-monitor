'use client'

import { useRouter, useSearchParams } from 'next/navigation'
import { useState } from 'react'

import { HitMatrix } from '@/components/charts/HitMatrix'
import { EvidenceModal } from '@/components/evidence/EvidenceModal'
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
import { MATRIX, MATRIX_COLUMNS, PROMPT_BY_ID, SAMPLE_RESPONSE, TOTALS } from '@/lib/fixtures'
import { OWN_BRAND_ID } from '@/lib/fixtures'

/** 样例样本属于这条提问 —— 点别的格子时要如实说明看到的不是那一格 */
const SAMPLE_PROMPT_ID = 101

export function ResponsesView() {
  const router = useRouter()
  const params = useSearchParams()
  const [tab, setTab] = useState('matrix')

  // 详情走查询参数而不是 /responses/123 —— 静态导出没有动态路由段（docs/28 §2.1）。
  // 好处顺带来了：模态开着时 URL 就是可分享的永久链接，刷新不丢、后退即关。
  const rid = params.get('rid')
  const pickedPrompt = Number(params.get('p') ?? SAMPLE_PROMPT_ID)

  const open = (promptId: number) => {
    router.push(`/responses/?p=${promptId}&rid=${SAMPLE_RESPONSE.id}`, { scroll: false })
  }
  const close = () => router.push('/responses/', { scroll: false })

  return (
    <>
      <PageHeader
        crumbs={['监测台', '回答明细']}
        title="回答明细"
        subtitle={`${TOTALS.nValid} 条有效样本 · 点任意格子查看该提问下的原始回答与证据`}
        actions={<Button>刷新</Button>}
      />

      <Tabs
        items={[
          { id: 'matrix', label: '矩阵' },
          { id: 'list', label: '列表', count: TOTALS.nValid },
        ]}
        active={tab}
        onChange={setTab}
      />

      <FilterBar>
        <SearchInput placeholder="搜索提问 / 关键词" />
        <Select label="状态" options={['全部状态', 'ok', 'error', 'empty', 'too_short']} />
        <Select label="平台" options={['全部平台', 'DeepSeek']} />
        <Button>重置</Button>
      </FilterBar>

      {tab === 'matrix' ? (
        <>
          <Panel
            title="提问 × 品牌 命中矩阵"
            subtitle="格子内为 命中 / 样本；空心 = 未提及；红框 = 本品挂零"
          >
            <HitMatrix
              rows={MATRIX}
              columns={MATRIX_COLUMNS}
              onPick={(promptId) => open(promptId)}
            />
          </Panel>

          <Panel inset flush>
            <p style={{ margin: 0, fontSize: 'var(--fs-sm)', color: 'var(--muted)', lineHeight: 1.7 }}>
              读法：上半区（国产 / 性价比类提问）本品与国产品牌成片命中、国际品牌成片空白；
              下半区（专业跑鞋 / 训练类）正好反过来。
              <strong style={{ color: 'var(--text)' }}>
                这个互补结构就是这套监测集给出的第一个结论 —— 也是「60%」这个数字背后的真相。
              </strong>
            </p>
          </Panel>
        </>
      ) : (
        <Panel title="回答列表" subtitle="每行一条抓取样本，可下钻到全文与截图" flush>
          <Table>
            <thead>
              <tr>
                <th>ID</th>
                <th>时间</th>
                <th>平台</th>
                <th>提问</th>
                <th>状态</th>
                <th>本品</th>
                <th>耗时</th>
                <th />
              </tr>
            </thead>
            <tbody>
              <tr>
                <td className="mono">#{SAMPLE_RESPONSE.id}</td>
                <td className="mono">{SAMPLE_RESPONSE.created_at.slice(0, 10)}</td>
                <td>{SAMPLE_RESPONSE.platform}</td>
                <td>{SAMPLE_RESPONSE.prompt_text}</td>
                <td>
                  <Badge tone="ok">{SAMPLE_RESPONSE.answer_status}</Badge>
                </td>
                <td>
                  <Badge tone="accent">
                    {SAMPLE_RESPONSE.mentions.some((m) => m.brand_id === OWN_BRAND_ID && m.mentioned)
                      ? '已提及'
                      : '未提及'}
                  </Badge>
                </td>
                <td className="mono">{SAMPLE_RESPONSE.latency_ms} ms</td>
                <td>
                  <button className={tableStyles.rowLink} onClick={() => open(SAMPLE_PROMPT_ID)}>
                    查看 ›
                  </button>
                </td>
              </tr>
            </tbody>
          </Table>
          <EmptyState>
            这一轮只搭框架，固定数据里只放了 1 条完整样本。
            <br />
            其余 {TOTALS.nValid - 1} 条接上 <code>GET /v1/responses</code> 后自动出现。
          </EmptyState>
        </Panel>
      )}

      {rid ? (
        <EvidenceModal
          response={SAMPLE_RESPONSE}
          notice={
            pickedPrompt === SAMPLE_PROMPT_ID
              ? undefined
              : `你点的是「${PROMPT_BY_ID.get(pickedPrompt)?.text ?? pickedPrompt}」，这里展示的是示例样本 #${SAMPLE_RESPONSE.id}。接上 GET /v1/responses?prompt_id= 后会换成该格子的真实样本。`
          }
          onClose={close}
        />
      ) : null}
    </>
  )
}
