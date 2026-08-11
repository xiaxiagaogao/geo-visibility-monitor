import { Badge, EmptyState, type BadgeTone } from '@/components/ui'
import type { Gap, GapPriority, GapTier } from '@/lib/l3/gaps'
import { formatFraction } from '@/lib/l3/rates'

import styles from './runs.module.css'

const TIER_LABEL: Record<GapTier, string> = {
  absent: '完全缺席',
  trailing: '明显落后',
}

const PRIORITY_TONE: Record<GapPriority, BadgeTone> = {
  high: 'danger',
  mid: 'warning',
  low: 'neutral',
}

/**
 * 覆盖缺口清单 —— 本品缺席或明显落后、且竞品在场的提问。
 *
 * **不进 tab，是刻意的**：这是这个产品里最接近「告诉我该干什么」的东西，
 * 输出可以直接交给推流团队。藏进第三个 tab 等于把唯一可执行的产出降级成附录。
 *
 * 只吃 props：排序与判级在 `lib/l3/gaps`，那边有 16 个测试守着。
 */
export function GapList({
  gaps,
  promptText,
  brandName,
  totalPrompts,
}: {
  gaps: Gap[]
  /** promptId → 提问正文，取自 run 快照 */
  promptText: Map<number, string>
  /** brandId → 品牌名，取自 run 快照（竞品被删了名字也还在） */
  brandName: Map<number, string>
  totalPrompts: number
}) {
  if (gaps.length === 0) {
    return (
      <EmptyState>
        <strong style={{ color: 'var(--text-secondary)' }}>这次没有覆盖缺口</strong>
        <span>
          {totalPrompts} 条提问里，本品都没有出现「自己缺席而竞品在场」的情况。
        </span>
      </EmptyState>
    )
  }

  return (
    <div>
      {gaps.map((g) => (
        <div key={g.promptId} className={styles.gapRow}>
          <div>
            <div className={styles.gapPrompt}>
              {promptText.get(g.promptId) ?? `提问 #${g.promptId}`}
            </div>
            <div className={styles.taskMeta}>
              <Badge tone={g.tier === 'absent' ? 'danger' : 'warning'}>
                {TIER_LABEL[g.tier]}
              </Badge>
              <span className="mono">本品 {formatFraction(g.ownM, g.n)}</span>
            </div>
          </div>

          <div className={styles.gapWho}>
            {/* 竞品名取自快照，按命中数降序 —— 第一个就是这条提问下最该盯的对手 */}
            {g.competitorsPresent
              .map((c) => `${brandName.get(c.brandId) ?? `#${c.brandId}`} ${c.m ?? 0}/${g.n}`)
              .join(' · ')}
          </div>

          <div className={styles.gapScore}>
            <Badge tone={PRIORITY_TONE[g.priority]}>{g.score}</Badge>
          </div>
        </div>
      ))}
    </div>
  )
}
