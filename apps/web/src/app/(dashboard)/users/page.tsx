import { UsersView } from './UsersView'

/**
 * 用户管理（A4）。**只有超管**：后端 `/v1/users/*` 挂的是 `require_superadmin`。
 *
 * 前端按角色隐藏侧栏入口只是体验，不是安全边界 —— 运营直接敲这个 URL
 * 也进得来，但接口会给 403，所以视图里先说清楚为什么。
 */
export default function UsersPage() {
  return <UsersView />
}
