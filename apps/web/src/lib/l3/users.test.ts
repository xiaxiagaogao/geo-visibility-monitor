import { describe, expect, it } from 'vitest'

import { canDeleteUser, needsWorkspace, roleLabel, willRevokeSessions, workspaceForRole } from './users'

describe('roleLabel', () => {
  it('三个角色都有中文名', () => {
    expect(roleLabel('superadmin')).toBe('超级管理员')
    expect(roleLabel('operator')).toBe('运营')
    expect(roleLabel('client')).toBe('客户')
  })

  it('未知角色原样显示，不吞掉', () => {
    // machine 身份的 role 是 'unknown'，映射不到就显示原文比显示「其他」有用
    expect(roleLabel('unknown')).toBe('unknown')
  })
})

describe('needsWorkspace', () => {
  it('只有客户需要', () => {
    expect(needsWorkspace('client')).toBe(true)
    expect(needsWorkspace('operator')).toBe(false)
    expect(needsWorkspace('superadmin')).toBe(false)
  })
})

describe('workspaceForRole —— 与后端 _validate_role_workspace 同口径', () => {
  it('超管/运营一律置 null，填了也不算数', () => {
    // 后端直接返回 None。表单要是给他们留输入框，填了不生效，
    // 而界面看起来像生效了 —— 这条用例把「别留那个框」钉死
    expect(workspaceForRole('superadmin', 5)).toBeNull()
    expect(workspaceForRole('operator', 5)).toBeNull()
  })

  it('客户带上 workspace 就用它', () => {
    expect(workspaceForRole('client', 2)).toBe(2)
  })

  it('客户没给 workspace = 不合法，返回 undefined', () => {
    // 没有 workspace 的客户什么都看不到 —— 与其建个废账号，不如当场拦下
    expect(workspaceForRole('client', null)).toBeUndefined()
  })

  it('客户给了 0 或负数也不合法', () => {
    expect(workspaceForRole('client', 0)).toBeUndefined()
    expect(workspaceForRole('client', -1)).toBeUndefined()
  })

  it('null 与 0 要分开 —— 0 不是「没填」，是个非法的 id', () => {
    expect(workspaceForRole('client', 0)).toBeUndefined()
    expect(workspaceForRole('client', 1)).toBe(1)
  })
})

describe('canDeleteUser', () => {
  it('不能删自己 —— 超管删光就没人能管用户了', () => {
    expect(canDeleteUser(1, 1)).toBe(false)
  })

  it('能删别人', () => {
    expect(canDeleteUser(1, 2)).toBe(true)
  })

  it('不知道自己是谁时一律不给删', () => {
    // machine 身份的 user_id 是 null。拿不准就别给这个按钮
    expect(canDeleteUser(null, 2)).toBe(false)
  })
})

describe('willRevokeSessions', () => {
  it('改密码会踢掉当前登录', () => {
    expect(willRevokeSessions({ password: 'new-password', wasActive: true })).toBe(true)
  })

  it('停用会踢掉当前登录', () => {
    expect(willRevokeSessions({ isActive: false, wasActive: true })).toBe(true)
  })

  it('本来就停用着，再停一次不算新的吊销', () => {
    expect(willRevokeSessions({ isActive: false, wasActive: false })).toBe(false)
  })

  it('启用不吊销 —— 那是恢复访问，不是撤销', () => {
    expect(willRevokeSessions({ isActive: true, wasActive: false })).toBe(false)
  })

  it('只改角色不吊销会话', () => {
    // 后端确实不吊销。所以「降权之后旧会话还带着旧角色吗」这个问题
    // 的答案是：会话里存的是 user_id，角色每次现查，所以降权立即生效
    expect(willRevokeSessions({ wasActive: true })).toBe(false)
  })

  it('空密码串不算改密', () => {
    expect(willRevokeSessions({ password: '', wasActive: true })).toBe(false)
  })
})
