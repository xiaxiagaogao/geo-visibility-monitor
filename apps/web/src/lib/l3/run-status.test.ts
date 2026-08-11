/**
 * run 状态的显示口径 —— 纯函数。
 *
 * 后端把状态派生成六档（services/tasks.py:derive_run_status），
 * 前端的责任是**不把它们揉回去**。揉回去的两种典型错法：
 *   · 把 partial 显示成「成功」—— 分母少了一截，所有比率静默偏高
 *   · 把 empty 显示成「成功」—— 一条 job 都没建，是配置问题不是成功
 */
import { describe, expect, it } from 'vitest'

import { runStatusTone, runStatusLabel } from './run-status'

describe('文案', () => {
  it.each([
    ['success', '全部成功'],
    ['partial', '部分成功'],
    ['failed', '全部失败'],
    ['running', '进行中'],
    ['pending', '排队中'],
    ['empty', '未产生任务'],
  ] as const)('%s → %s', (status, label) => {
    expect(runStatusLabel(status)).toBe(label)
  })

  it('partial 的文案不能是「成功」', () => {
    // 部分成功报成成功，用户会以为分母是全的 —— 而它少了一截，比率全部偏高。
    expect(runStatusLabel('partial')).not.toBe('全部成功')
    expect(runStatusLabel('partial')).toContain('部分')
  })

  it('empty 的文案不能暗示成功', () => {
    // 建了 run 却一条 job 都没有，是提问集或平台为空 —— 配置问题。
    const label = runStatusLabel('empty')
    expect(label).not.toContain('成功')
  })

  it('没有 run 时给「从未运行」，不是空字符串', () => {
    // 空字符串会让那一格看起来像加载失败。
    expect(runStatusLabel(null)).toBe('从未运行')
  })
})

describe('色调', () => {
  it('partial 是警告色，不是成功色', () => {
    expect(runStatusTone('partial')).toBe('warning')
    expect(runStatusTone('partial')).not.toBe('ok')
  })

  it('empty 也是警告 —— 它是配置问题，需要人看一眼', () => {
    expect(runStatusTone('empty')).toBe('warning')
  })

  it('failed 是危险色', () => {
    expect(runStatusTone('failed')).toBe('danger')
  })

  it('success 才是成功色', () => {
    expect(runStatusTone('success')).toBe('ok')
  })

  it('进行中与排队中都是中性 —— 还没有结论，不该染成红或绿', () => {
    expect(runStatusTone('running')).toBe('neutral')
    expect(runStatusTone('pending')).toBe('neutral')
  })

  it('没有 run 时是中性', () => {
    expect(runStatusTone(null)).toBe('neutral')
  })
})
