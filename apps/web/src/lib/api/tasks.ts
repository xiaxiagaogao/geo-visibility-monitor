/**
 * 检测任务与运行。字段以 `docs/API.md` §8.5 为准。
 */
import type { Task } from '../types'
import { apiFetch } from './client'

export interface TaskListResult {
  items: Task[]
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
