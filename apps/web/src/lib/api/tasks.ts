/**
 * 检测任务与运行。字段以 `docs/API.md` §8.5 为准。
 */
import type { Run, RunDetail, Task } from '../types'
import { apiFetch } from './client'

export interface TaskListResult {
  items: Task[]
  total: number
}

export interface RunListResult {
  items: Run[]
  total: number
}

/**
 * 任务列表。**不传 brand_id 时服务端按 workspace 自动收敛** ——
 * 前端不必也不应该自己加过滤（API.md §3）。
 */
export async function listTasks(params: {
  brandId?: number
  limit?: number
  offset?: number
} = {}): Promise<TaskListResult> {
  return apiFetch<TaskListResult>('/v1/tasks', {
    query: { brand_id: params.brandId, limit: params.limit, offset: params.offset },
  })
}

export interface TaskCreateInput {
  brand_id: number
  name: string
  platforms: string[]
  samples: number
}

/** 建任务。仅超管/运营；写操作，`apiFetch` 会带上 CSRF 头。 */
export async function createTask(input: TaskCreateInput): Promise<Task> {
  return apiFetch<Task>('/v1/tasks', { method: 'POST', body: input })
}

/**
 * 单个任务。
 *
 * **404 同时意味着「不存在」和「不属于你」** —— 后端刻意不区分（防枚举，
 * API.md §2.2）。调用方按「没有这条」处理，别提示「无权访问」，
 * 那等于把「这个 id 存在」这个事实透出去了。
 */
export async function getTask(taskId: number): Promise<Task> {
  return apiFetch<Task>(`/v1/tasks/${taskId}`)
}

/** 该任务的执行历史，按 `created_at` 降序 —— run 切换器的数据源。 */
export async function listRuns(
  taskId: number,
  params: { limit?: number; offset?: number } = {},
): Promise<RunListResult> {
  return apiFetch<RunListResult>(`/v1/tasks/${taskId}/runs`, {
    query: { limit: params.limit, offset: params.offset },
  })
}

/**
 * 某次运行的详情，**带两份快照**（`prompts` / `competitors`）。
 *
 * 矩阵的行、缺口清单的行标题都取自 `prompts[].prompt_text`，
 * 不必再打一次 `/v1/prompts` —— 而且也**不该**打：`/v1/prompts` 返回的是
 * 提问词的**当前**正文，拿它当历史 run 的行标题，改过名的提问会被静默改写。
 */
export async function getRun(runId: number): Promise<RunDetail> {
  return apiFetch<RunDetail>(`/v1/runs/${runId}`)
}

export interface TaskUpdateInput {
  name?: string
  platforms?: string[]
  samples?: number
  is_active?: boolean
}

/**
 * 改任务。**不含 `brand_id`** —— 后端 `TaskUpdate` 里就没有这个字段，
 * 任务过不了户（API.md §8.5）。
 *
 * 改 `platforms` / `samples` **只影响以后的运行**：每次 run 都有自己的
 * platforms 快照，历史那些不会被改写。
 *
 * `is_active=false` 之后**发起运行会被拒**（400）—— 这是 2026-08-12 补的，
 * 在那之前停用只是个徽章。
 */
export async function updateTask(taskId: number, input: TaskUpdateInput): Promise<Task> {
  return apiFetch<Task>(`/v1/tasks/${taskId}`, { method: 'PATCH', body: input })
}

/**
 * **我能看到的**最新一次运行 —— 客户首页分流用。
 *
 * 「我能看到的」是服务端按 principal 收敛的，不是全局最新：客户拿到的一定是
 * 自己 workspace 里的。所以前端不必也不应该自己加过滤。
 *
 * **一次运行都没有时是 404**，不是空对象 —— 调用方必须显式处理这一支，
 * 否则新客户第一次登录会卡在一个永远转不完的「正在进入…」。
 *
 * 为什么不用 `/v1/tasks` 取第一条代替：那个列表按 task 的 `created_at` 排序，
 * 不是按最近一次运行。客户有两个任务、而新建的那个还没跑过时，
 * 拿列表第一条会把他送进一个空页面。
 */
export async function getLatestRun(): Promise<RunDetail> {
  return apiFetch<RunDetail>('/v1/runs/latest')
}

/**
 * 发起一次运行。仅超管/运营。
 *
 * **返回的是 `RunOut` 而不是详情**，且此刻 job 全是 `pending` ——
 * 所以 `status` 会是 `pending`，`n_jobs` 是刚建出来的数量。
 * 想要快照得再打一次 `getRun`。
 *
 * 这一步是真的建 job、真的消耗额度，和「建任务」不是一回事。
 */
export async function startRun(taskId: number): Promise<Run> {
  return apiFetch<Run>(`/v1/tasks/${taskId}/runs`, { method: 'POST' })
}
