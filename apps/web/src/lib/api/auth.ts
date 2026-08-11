/**
 * 身份相关的三个调用。字段以 `docs/API.md` §2 为准。
 */
import { apiFetch, setCsrfToken } from './client'

export type Role = 'superadmin' | 'operator' | 'client'

export interface Me {
  user_id: number | null
  email: string | null
  role: Role | 'unknown'
  /** **只有 client 非空**，是他能看到的品牌范围 */
  workspace_id: number | null
  /** `user` = 会话；`machine` = 共享密钥 / QA 后门 */
  kind: 'user' | 'machine'
  /** 写操作要回填到 `X-CSRF-Token`。machine 身份不走 Cookie，为 null */
  csrf_token: string | null
}

/**
 * 登录。**失败一律 401 且只有一句话** —— 后端不区分「用户不存在 / 密码错 /
 * 账号停用」，前端也不许据此提示「该邮箱未注册」，那等于把账号枚举做到 UI 上。
 */
export async function login(email: string, password: string): Promise<Me> {
  const me = await apiFetch<Me>('/v1/auth/login', {
    method: 'POST',
    body: { email, password },
  })
  setCsrfToken(me.csrf_token)
  return me
}

/** 刷新页面后内存里的 csrf 就没了，靠这个端点重新拿，不必让用户重新登录。 */
export async function fetchMe(): Promise<Me> {
  const me = await apiFetch<Me>('/v1/auth/me')
  setCsrfToken(me.csrf_token)
  return me
}

export async function logout(): Promise<void> {
  await apiFetch('/v1/auth/logout', { method: 'POST' })
  setCsrfToken(null)
}

/** 能改配置 / 发起抓取的角色。客户是纯只读。 */
export function canWrite(me: Me | null): boolean {
  return me?.role === 'superadmin' || me?.role === 'operator'
}
