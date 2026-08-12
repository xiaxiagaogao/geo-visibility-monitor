/**
 * 提问词。字段以 `docs/API.md` §6 为准。
 */
import type { Prompt } from '../types'
import { apiFetch } from './client'

export interface PromptListResult {
  items: Prompt[]
  total: number
}

/**
 * 某品牌的提问词。
 *
 * `activeOnly` 默认 false —— 管理界面要看见**停用的那些**，否则用户会以为
 * 它们被删了。发起 run 时后端只取 `is_active=true`（`services/tasks.create_run`），
 * 那是另一回事。
 *
 * **`category` 没有服务端过滤参数**（API.md §6）—— 拿回来自己归类。
 */
export async function listPrompts(params: {
  brandId: number
  activeOnly?: boolean
}): Promise<PromptListResult> {
  return apiFetch<PromptListResult>('/v1/prompts', {
    query: { brand_id: params.brandId, active_only: params.activeOnly },
  })
}

export interface PromptCreateInput {
  brand_id: number
  text: string
  category?: string | null
  is_active?: boolean
}

export async function createPrompt(input: PromptCreateInput): Promise<Prompt> {
  return apiFetch<Prompt>('/v1/prompts', { method: 'POST', body: input })
}

/** 改提问词。PATCH 是增量 —— 只传要改的字段。 */
export async function updatePrompt(
  promptId: number,
  input: { text?: string; category?: string | null; is_active?: boolean },
): Promise<Prompt> {
  return apiFetch<Prompt>(`/v1/prompts/${promptId}`, { method: 'PATCH', body: input })
}

/**
 * 删提问词。**这会改写历史，不只是「以后不问了」。**
 *
 * `crawl_jobs.prompt_id` 是 `ON DELETE CASCADE`，所以删一条提问词会连带删掉
 * 它的全部 job → response → mention。后果是：
 *
 *   · 历史 run 的**快照行还在**（`run_prompts.prompt_id` 是普通整数、
 *     没有外键，这是刻意的），所以矩阵里那一行不会消失
 *   · 但那一行的 `n` 掉到 0，变成「不可算」
 *   · 而那次 run 的 `n_valid` 少了一截 —— **总提及率会当场变**
 *
 * 「以后不再问这条」应该用 `updatePrompt(id, { is_active: false })`，
 * 它只影响未来的 run，一个历史数字都不动。
 */
export async function deletePrompt(promptId: number): Promise<void> {
  await apiFetch(`/v1/prompts/${promptId}`, { method: 'DELETE' })
}
