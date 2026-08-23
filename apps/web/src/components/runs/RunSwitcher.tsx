'use client'

import { Mark, markTone, Select } from '@/components/record'
import { runStatusLabel, runStatusTone } from '@/lib/l3/run-status'
import type { Run } from '@/lib/types'

import styles from './runs.module.css'

/**
 * run 切换器 —— 「我现在看的是哪一次运行」。
 *
 * 只吃 props（`components/` 不许 fetch），换 run 由调用方决定怎么做，
 * 这里不碰路由。
 *
 * **用原生 `<select>` 而不是自绘下拉。** 自绘要自己处理焦点、外部点击、
 * 方向键、Esc，几乎必然做漏一样；而这个控件的全部职责就是「从 N 个里选一个」。
 * 状态的颜色信号由旁边的 `<Badge>` 给，两者合起来就是设计稿那颗
 * `[2026-08-02 ✓ 35条 ▾]`，但键盘和读屏是白拿的。
 */
export function RunSwitcher({
  runs,
  currentRunId,
  onChange,
  disabled,
}: {
  runs: Run[]
  currentRunId: number
  onChange: (runId: number) => void
  disabled?: boolean
}) {
  const current = runs.find((r) => r.id === currentRunId)

  return (
    <div className={styles.switcher}>
      <Select
        className={styles.select}
        value={currentRunId}
        onChange={(e) => onChange(Number(e.target.value))}
        disabled={disabled}
        aria-label="选择一次运行"
      >
        {runs.map((r) => (
          <option key={r.id} value={r.id}>
            {runLabel(r)}
          </option>
        ))}
      </Select>

      {current ? (
        <Mark tone={markTone(runStatusTone(current.status))} dot>
          {runStatusLabel(current.status)}
        </Mark>
      ) : null}
    </div>
  )
}

/**
 * `2026-08-02 10:41 · 35 个采样`
 *
 * **时间直接切 ISO 字符串，不走 `toLocaleString`。** 这是客户端组件但仍会
 * 服务端渲染一次，locale / 时区在两侧不一定一致，渲染出两个不同的字符串
 * 就是 hydration mismatch。
 *
 * 状态不进这行文字：它已经在旁边的 Badge 上，写两遍会让 40 个字符的
 * option 更难扫。
 */
function runLabel(run: Run): string {
  const t = run.created_at.slice(0, 16).replace('T', ' ')
  // n_jobs 是**建出来的采样数**，不是有效样本数 —— 后者要看 KPI 里的分母。
  // 所以这里写「采样」不写「条」，避免和 n_valid 混成一个数。
  return `${t} · ${run.n_jobs} 个采样`
}
