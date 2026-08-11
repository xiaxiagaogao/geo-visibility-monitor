/**
 * run 状态的显示口径 —— 纯函数，不碰 fetch 与 React。
 *
 * 后端把状态派生成六档（`services/tasks.py:derive_run_status`），
 * **前端的责任是不把它们揉回去**。
 *
 * 最容易揉错的是 `partial` 与 `empty`：
 *   · `partial` 报成「成功」 → 用户以为分母是全的，而它少了一截，所有比率偏高
 *   · `empty`   报成「成功」 → 一条 job 都没建（提问集或平台为空），是配置问题
 */
import type { RunStatus } from '../types'

/** 徽章色调，对应 `components/ui` 的 `Badge tone` */
export type Tone = 'ok' | 'warning' | 'danger' | 'neutral'

const LABELS: Record<RunStatus, string> = {
  success: '全部成功',
  partial: '部分成功',
  failed: '全部失败',
  running: '进行中',
  pending: '排队中',
  empty: '未产生任务',
}

const TONES: Record<RunStatus, Tone> = {
  success: 'ok',
  // 部分成功不是成功。染成绿色等于告诉用户「这次没问题」，
  // 而它的分母比预期少，后面所有比率都偏高。
  partial: 'warning',
  failed: 'danger',
  // 还没有结论的两档保持中性 —— 染成红或绿都是在替用户下判断。
  running: 'neutral',
  pending: 'neutral',
  // 配置问题，需要人看一眼，所以给警告而不是中性。
  empty: 'warning',
}

export function runStatusLabel(status: RunStatus | null): string {
  // 空字符串会让那一格看起来像加载失败，明说「从未运行」。
  if (status === null) return '从未运行'
  return LABELS[status] ?? status
}

export function runStatusTone(status: RunStatus | null): Tone {
  if (status === null) return 'neutral'
  return TONES[status] ?? 'neutral'
}
