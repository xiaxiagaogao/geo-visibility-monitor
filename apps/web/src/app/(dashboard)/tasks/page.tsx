import { TasksView } from './TasksView'

/**
 * 任务列表 —— 超管/运营的首页（客户走 `/` 直接进最新 run）。
 *
 * 列表接口**服务端按 workspace 自动收敛**，前端不必也不应该自己加过滤
 * （API.md §3）。
 */
export default function TasksPage() {
  return <TasksView />
}
