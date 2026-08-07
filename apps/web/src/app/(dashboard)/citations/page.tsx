import { EmptyState, Panel, PanelNote } from '@/components/ui'

/**
 * 引用分析。
 *
 * **这一页是悬着的**：真实 `citations` 表里到底有多少数据还没核实过（docs/29 §10）。
 * 抓取链路确实会从 SSE 里解析引用（crawl_runner.py 落 Citation 行），
 * 但样本抓取时 DeepSeek 是否开了联网检索决定了实际有没有引用。
 *
 * 所以这里**故意只放空态**，不用固定数据编一张漂亮的 Top10 表 ——
 * 编出来的图表会让人以为这块能力已经具备。
 * 核实后：有数据就补来源明细表；普遍为空就整页降级并从侧栏隐藏。
 *
 * 另：GeoMonitor 的「平台引用分布」环形图不做 ——
 * 我们只有 DeepSeek，单平台的构成比是一根 100% 的条，画出来是假装有多样性。
 */
export default function CitationsPage() {
  return (
    <>
      <Panel title="引用来源" subtitle="citations 聚合 · 按来源域名去重">
        <EmptyState>
          <strong style={{ color: 'var(--text-secondary)' }}>尚未接入</strong>
          <span>
            真实引用量还没核实。接上 <code>GET /v1/responses</code> 聚合 <code>citations</code> 后，
            <br />
            这里出「来源 / 覆盖提问数 / 引用次数」的排行表。
          </span>
        </EmptyState>
      </Panel>

      <PanelNote>
        这一页留空是有意的：与其用固定数据编一张 Top10 表，不如诚实说还没接。
        编出来的图表会让人误以为这块能力已经具备 —— 而这个产品的全部可信度，
        建立在「屏幕上每个数字都能追到原文」上面。
      </PanelNote>
    </>
  )
}
