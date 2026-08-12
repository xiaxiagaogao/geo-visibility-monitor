/**
 * 用户管理（A4）。**整组接口只有超管能用**（后端 `require_superadmin`）。
 *
 * 字段以 `apps/api/app/api/users.py` 为准 —— 这组 schema 定义在路由文件里，
 * 不在 `schemas/`，所以 API.md §6 没有它的字段表。
 */
import { apiFetch } from './client'
import type { Role } from './auth'

/**
 * `apps/api/app/api/users.py :: UserOut`
 *
 * 和 `Me` 不是一回事：`Me` 是「我是谁」（带 csrf_token、kind），
 * 这个是「用户表里的一行」（带 is_active、created_at、last_login_at）。
 */
export interface User {
  id: number
  email: string
  role: Role | string
  /** **只有 client 非空** —— 超管/运营的会被后端强制置 null */
  workspace_id: number | null
  is_active: boolean
  created_at: string
  /** 从没登录过就是 null */
  last_login_at: string | null
}

export interface UserListResult {
  items: User[]
  total: number
}

export async function listUsers(): Promise<UserListResult> {
  return apiFetch<UserListResult>('/v1/users')
}

export interface UserCreateInput {
  email: string
  /** 最短长度由后端定（`core/auth.MIN_PASSWORD_LEN`），前端不复制那个数字 */
  password: string
  role: Role
  /** 只有 client 要传；其余角色传了也会被后端置 null */
  workspace_id?: number | null
}

/** 建用户。**邮箱重复是 409**，要单独给一句话，不然用户只看到「创建失败」。 */
export async function createUser(input: UserCreateInput): Promise<User> {
  return apiFetch<User>('/v1/users', { method: 'POST', body: input })
}

/**
 * 改用户。PATCH 是增量 —— 只传要改的字段。
 *
 * ⚠️ **改 `password` 或把 `is_active` 改成 false，后端会吊销该用户全部会话**
 * （`revoke_all_sessions`）——否则旧会话继续有效，等于没改。
 * 这是个用户看不见的副作用，界面必须先说出来。
 */
export async function updateUser(
  userId: number,
  input: {
    role?: Role
    workspace_id?: number | null
    is_active?: boolean
    password?: string
  },
): Promise<User> {
  return apiFetch<User>(`/v1/users/${userId}`, { method: 'PATCH', body: input })
}

/** 删用户。**删自己是 400** —— 超管删光后没人能管用户，只能进库改。 */
export async function deleteUser(userId: number): Promise<void> {
  await apiFetch(`/v1/users/${userId}`, { method: 'DELETE' })
}
