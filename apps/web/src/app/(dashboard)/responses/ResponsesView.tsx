'use client'

import { useSearchParams } from 'next/navigation'

import { HighlightedText } from '@/components/evidence/HighlightedText'
import { Badge, Degraded, EmptyState, Panel, Table, ui } from '@/components/ui'
import { OWN_BRAND_ID, SAMPLE_RESPONSE } from '@/lib/fixtures'
import { brandName, promptText } from '@/lib/selectors'

import styles from './responses.module.css'

/** 样例样本属于这条提问 —— 点别的格子时要如实说明看到的不是那一格 */
const SAMPLE_PROMPT_ID = 101

export function ResponsesView() {
  const params = useSearchParams()

  // 详情走查询参数而不是 /responses/123 —— 静态导出没有动态路由段（docs/28 §2.1）。
  // 顺带好处：URL 就是可分享的永久链接，刷新不丢。
  const pickedPrompt = Number(params.get('p') ?? SAMPLE_PROMPT_ID)
  const mismatched = pickedPrompt !== SAMPLE_PROMPT_ID

  const r = SAMPLE_RESPONSE
  const hits = r.mentions.filter((m) => m.mentioned)

  return (
    <div className={styles.split}>
      <Panel>
        {mismatched ? (
          <p className={styles.notice}>
            你点的是「{promptText(pickedPrompt)}」，这里展示的是示例样本 #{r.id}。
            接上 <code>GET /v1/responses?prompt_id=</code> 后会换成该格子的真实样本。
          </p>
        ) : null}

        <div className={styles.answerHead}>
          <span className={styles.platformTag}>
            <span className={styles.platformDot} />
            DeepSeek
          </span>
          <span className={styles.runMeta}>#{r.id}</span>
          <span className={styles.runMeta}>{r.created_at.slice(0, 16).replace('T', ' ')}</span>
          <span style={{ flex: 1 }} />
          <Badge tone="ok" dot>
            已提及
          </Badge>
          <Degraded>暂无排名</Degraded>
          <Degraded>暂无情感</Degraded>
        </div>

        <h2 className={styles.question}>{r.prompt_text}</h2>

        <HighlightedText
          text={r.full_text}
          highlights={[]}
          className={styles.answerBody}
          markClassName={styles.hl}
        />

        <p className={styles.pending}>
          命中位置内联高亮尚未开启：后端 <code>mentions</code> 表还没有{' '}
          <code>first_offset</code> / <code>matched_term</code> 两列。
          前端不会自己去正文里重找品牌名 —— 那会和 L1 标注口径分叉。
        </p>

        <p className={styles.sectionLabel}>L1 标注 · 命中品牌（{hits.length}）</p>
        <Table>
          <thead>
            <tr>
              <th>品牌</th>
              <th>类型</th>
              <th>首次位置</th>
              <th>出场顺位</th>
            </tr>
          </thead>
          <tbody>
            {hits.map((m) => (
              <tr key={m.id}>
                <td style={m.brand_id === OWN_BRAND_ID ? { color: 'var(--accent)', fontWeight: 600 } : undefined}>
                  {brandName(m.brand_id)}
                  {m.brand_id === OWN_BRAND_ID ? '（本品）' : ''}
                </td>
                <td>
                  <Badge>{m.mention_type}</Badge>
                </td>
                <td>
                  <Badge>{m.position_bucket ?? '—'}</Badge>
                </td>
                <td>
                  {m.position_rank !== null ? (
                    <span className={ui.numeric}>#{m.position_rank}</span>
                  ) : (
                    <Degraded>未排名</Degraded>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </Table>

        <p className={styles.sectionLabel}>引用来源（{r.citations.length}）</p>
        {r.citations.length === 0 ? (
          <EmptyState>本样本无解析到引用。</EmptyState>
        ) : (
          <Table>
            <tbody>
              {r.citations.map((c) => (
                <tr key={c.id}>
                  <td>{c.title ?? c.url}</td>
                  <td style={{ color: 'var(--text-tertiary)' }}>{c.domain}</td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Panel>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-4)' }}>
        <Panel title="执行元数据">
          <MetaRow k="执行模式" v="browser" />
          <MetaRow k="耗时" v={`${r.latency_ms} ms`} />
          <MetaRow k="answer_status" v={r.answer_status ?? '—'} />
          <MetaRow k="标注版本" v={r.annotator_version ?? '—'} />
          <MetaRow k="任务" v={`#${r.job_id}`} />
          <div className={styles.metaRow}>
            <span className={styles.metaKey}>出场顺位</span>
            <Degraded>暂无排名数据</Degraded>
          </div>
          <div className={styles.metaRow}>
            <span className={styles.metaKey}>情感</span>
            <Degraded>暂无情感数据</Degraded>
          </div>
          <div className={styles.metaRow}>
            <span className={styles.metaKey}>别名命中</span>
            <Degraded>待后端补 matched_term</Degraded>
          </div>
        </Panel>

        <Panel title="回答截图">
          <div className={styles.shot}>
            <span>完整回答区域截图（隐藏侧栏）</span>
            <span className={styles.shotPath}>{r.screenshot_path}</span>
          </div>
          <p style={{ fontSize: 'var(--fs-xs)', color: 'var(--text-tertiary)', margin: '10px 0 0' }}>
            经 <code>/v1/media/screenshots/</code> 取，靠 Cookie 鉴权。
            不保留 DeepSeek 对话 URL · 会话抓完即删。
          </p>
        </Panel>
      </div>
    </div>
  )
}

function MetaRow({ k, v }: { k: string; v: string }) {
  return (
    <div className={styles.metaRow}>
      <span className={styles.metaKey}>{k}</span>
      <span className={styles.metaVal}>{v}</span>
    </div>
  )
}
