/**
 * 首页分流的判定（A8）——「登录之后该把这个人送到哪儿」。
 *
 * 抽出来单独测，是因为它有一个**反向写就出事、而且不会报错**的地方：
 * machine 身份（`X-API-Key` / QA 后门）的 `role` 是 `'unknown'`，
 * 权限等同超管。用 `!canWrite(me)` 取反来判「是不是客户」，
 * 会把它错分到客户那条路上 —— 然后拿一个不存在的 workspace 去要最新 run。
 *
 * 纯函数，不碰 fetch 与 React（路由跳转由调用方做）。
 */

/** 任务列表 —— 超管/运营的工作台，也是所有兜底的落点 */
export const TASKS_ROUTE = '/tasks'

/**
 * 要不要先去查「我能看到的最新一次运行」。
 *
 * **只有客户要。** 超管/运营管多个客户品牌，任务列表就是他们的工作台，
 * 多打一次 `/v1/runs/latest` 既慢又没意义 —— 全局最新那一条大概率
 * 不是他现在关心的那个客户。
 */
export function needsLatestRun(role: string | null | undefined): boolean {
  return role === 'client'
}

/**
 * 首页的落点。
 *
 * `latestRunTaskId` 为 `null` 表示**没有可见运行**（`/v1/runs/latest` 返回 404）。
 * 那是新客户的正常状态，不是错误 —— 退回任务列表，那里已经有「还没有任务 /
 * 从未运行」的文案。在首页再写一套同义的，两份迟早会漂。
 *
 * 落到 `/tasks/{id}` 而不是 `/tasks/{id}/runs/{runId}`：两者此刻显示同一次运行
 * （任务详情自动落到最新），但钉死 run 的 URL 明天就不是最新的了，
 * 而首页的语义是「给我看最新的」。
 */
export function homeRoute(
  role: string | null | undefined,
  latestRunTaskId: number | null,
): string {
  if (!needsLatestRun(role)) return TASKS_ROUTE
  if (latestRunTaskId === null) return TASKS_ROUTE
  return `${TASKS_ROUTE}/${latestRunTaskId}`
}
