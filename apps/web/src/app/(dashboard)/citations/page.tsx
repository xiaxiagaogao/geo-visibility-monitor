import { EmptyState, Panel, PanelNote } from '@/components/ui'

/**
 * 引用分析。
 *
 * 写这页时这里标着「悬着的，真实引用量还没核实」。**现在核实完了，答案是零。**
 *
 * `citations` 全库 0 行。根因不是解析 bug —— 抓取链路确实会从 SSE 里解析引用，
 * 是**样本抓取时从未开过联网搜索**，DeepSeek 不联网就不产生引用。
 * 所以这不是「加个字段 / 修个解析」能解决的：要有数据必须开联网 + 重抓，
 * 而重抓会破坏现有基线的可比性（API.md §9）。
 *
 * 结论：**这一页当前做不了**，不是「还没做」。整页删除与侧栏条目摘除排在下一轮，
 * 本轮只把文案从「尚未接入」改成实话 —— 前者会让人以为在排队上线。
 *
 * 另：GeoMonitor 的「平台引用分布」环形图不做 ——
 * 我们只有 DeepSeek，单平台的构成比是一根 100% 的条，画出来是假装有多样性。
 */
export default function CitationsPage() {
  return (
    <>
      <Panel title="引用来源" subtitle="citations 聚合 · 按来源域名去重">
        <EmptyState>
          <strong style={{ color: 'var(--text-secondary)' }}>当前无法提供</strong>
          <span>
            采集样本时未开启联网搜索，模型回答里不含引用来源，
            <br />
            因此没有可聚合的数据。这不是采集故障，也不是数据还没到。
          </span>
        </EmptyState>
      </Panel>

      <PanelNote>
        要让这一页立起来，需要开启联网搜索后重新采集 —— 而重采会使新数据与现有基线
        不可比。在做出这个取舍之前，这里不放任何图表：编出来的 Top10
        会让人误以为这块能力已经具备，而这个产品的全部可信度，
        建立在「屏幕上每个数字都能追到原文」上面。
      </PanelNote>
    </>
  )
}
