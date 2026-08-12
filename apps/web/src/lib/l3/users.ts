/**
 * 用户与角色的判定（A4）。
 *
 * 抽出来单独测，因为有两条**写反了不会报错、只会悄悄出事**的规则：
 *
 *   1. `client` 必须有 `workspace_id`，而超管/运营的会被后端**强制置 null**
 *      —— 表单如果给他们留着 workspace 输入框，填了也不生效，
 *      而界面看起来像生效了。
 *   2. 不能删自己。后端是 400，但前端得先不给这个按钮 ——
 *      超管把自己删了就没人能管用户了，只能进库改。
 *
 * 纯函数，不碰 fetch 与 React。
 */
import type { Role } from '../api/auth'

export const ROLE_LABEL: Record<string, string> = {
  superadmin: '超级管理员',
  operator: '运营',
  client: '客户',
}

/** 可分配的角色。顺序即表单里的顺序：权限从大到小 */
export const ASSIGNABLE_ROLES: Role[] = ['superadmin', 'operator', 'client']

export function roleLabel(role: string): string {
  return ROLE_LABEL[role] ?? role
}

/**
 * 这个角色要不要 workspace。
 *
 * **只有客户要。** 超管与运营看全部数据，给他们带一个 workspace_id
 * 只会误导后来读库的人 —— 后端 `_validate_role_workspace` 直接返回 None。
 */
export function needsWorkspace(role: string): boolean {
  return role === 'client'
}

/**
 * 按角色归一化 workspace —— **照抄后端 `_validate_role_workspace`**。
 *
 * 返回 `undefined` 表示「这个组合不合法」（客户没给 workspace），
 * 调用方据此拦下提交，而不是等后端回一个 400。
 */
export function workspaceForRole(
  role: string,
  workspaceId: number | null,
): number | null | undefined {
  if (!needsWorkspace(role)) return null
  if (workspaceId === null || !Number.isInteger(workspaceId) || workspaceId <= 0) {
    return undefined
  }
  return workspaceId
}

/**
 * 能不能删这个用户。
 *
 * 唯一的禁止项是**删自己**：超管删光之后没人能管用户，只能进库改。
 * 后端也拦（400），这里拦是为了不给一个点了必然失败的按钮。
 */
export function canDeleteUser(myUserId: number | null, targetUserId: number): boolean {
  if (myUserId === null) return false
  return myUserId !== targetUserId
}

/**
 * 改这个用户会不会踢掉他当前的登录。
 *
 * 后端在**改密**或**停用**时调 `revoke_all_sessions` —— 否则旧会话继续有效，
 * 等于没改。这是个用户看不见的副作用，界面必须先说出来。
 */
export function willRevokeSessions(input: {
  password?: string | null
  isActive?: boolean | null
  wasActive: boolean
}): boolean {
  if (input.password) return true
  return input.isActive === false && input.wasActive
}
