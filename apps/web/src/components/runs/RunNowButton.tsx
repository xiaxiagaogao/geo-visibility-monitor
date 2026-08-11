'use client'

import { Button } from '@/components/ui'

import styles from './runs.module.css'

/**
 * 「立即运行」—— 两段式确认。
 *
 * 只吃 props，真正发请求的是调用方（`components/` 不许 fetch）。
 *
 * **为什么要确认这一步：** 这个按钮和「新建任务」不是一回事 ——
 * 它会真的建 job、真的去抓、真的消耗额度，而且**建了就撤不回来**
 * （没有取消 run 的接口）。一次误点在任务列表上看不出来，
 * 要等一批 job 跑完才发现。
 *
 * 不用 `window.confirm`：它会阻塞主线程、样式不受控、移动端体验差，
 * 而且没法把「这次要建多少个 job」这种关键信息写进去。
 */
export function RunNowButton({
  armed,
  onArm,
  onCancel,
  onConfirm,
  busy,
  /** 上一次运行建了多少个 job —— 给用户一个量级参照，没有历史就不显示 */
  lastJobCount,
  disabled,
}: {
  armed: boolean
  onArm: () => void
  onCancel: () => void
  onConfirm: () => void
  busy?: boolean
  lastJobCount?: number
  disabled?: boolean
}) {
  if (!armed) {
    return (
      <Button primary onClick={onArm} disabled={disabled}>
        立即运行
      </Button>
    )
  }

  return (
    <div className={styles.confirm} role="group" aria-label="确认发起运行">
      <span className={styles.confirmText}>
        会按<strong>当前</strong>的提问集与竞品集冻结一份快照，然后真的建 job 去抓
        {/* 说「上次」而不是「这次会建 N 个」—— 提问集可能已经改了，
            报一个算出来的精确数字反而是在编。量级参照够用了。 */}
        {lastJobCount ? `（上次建了 ${lastJobCount} 个）` : ''}。发起后无法取消。
      </span>
      <Button primary onClick={onConfirm} disabled={busy || disabled}>
        {busy ? '发起中…' : '确认发起'}
      </Button>
      <Button onClick={onCancel} disabled={busy}>
        取消
      </Button>
    </div>
  )
}
