import { describe, expect, it } from 'vitest'

import { homeRoute, needsLatestRun } from './home'

describe('needsLatestRun', () => {
  it('只有客户要查最新 run', () => {
    expect(needsLatestRun('client')).toBe(true)
    expect(needsLatestRun('operator')).toBe(false)
    expect(needsLatestRun('superadmin')).toBe(false)
  })

  it('machine 身份的 unknown **不是**客户', () => {
    // 这是这个文件存在的理由：machine（X-API-Key / QA 后门）权限等同超管，
    // 但 role 是 'unknown'。用 `!canWrite(me)` 取反判客户会把它错分过去，
    // 然后拿一个不存在的 workspace 去要最新 run
    expect(needsLatestRun('unknown')).toBe(false)
  })

  it('还没拿到身份时不查 —— 不拿 undefined 当客户', () => {
    expect(needsLatestRun(undefined)).toBe(false)
    expect(needsLatestRun(null)).toBe(false)
  })
})

describe('homeRoute', () => {
  it('超管 / 运营去任务列表，不管有没有最新 run', () => {
    expect(homeRoute('operator', 7)).toBe('/tasks')
    expect(homeRoute('superadmin', null)).toBe('/tasks')
  })

  it('客户去自己那条最新运行所在的任务', () => {
    expect(homeRoute('client', 27)).toBe('/tasks/27')
  })

  it('客户一次都没跑过时退回任务列表 —— 404 是正常状态不是错误', () => {
    // 新客户第一次登录就是这个形态。不处理这一支的话，
    // 他会卡在一个永远转不完的「正在进入…」
    expect(homeRoute('client', null)).toBe('/tasks')
  })

  it('身份未知时退回任务列表 —— 列表接口自己会按 workspace 收敛', () => {
    expect(homeRoute(undefined, 27)).toBe('/tasks')
  })
})
