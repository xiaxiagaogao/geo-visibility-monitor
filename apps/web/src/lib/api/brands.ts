/**
 * 品牌。字段以 `docs/API.md` §6 为准。
 */
import type { Brand } from '../types'
import { apiFetch } from './client'

export interface BrandListResult {
  items: Brand[]
  total: number
}

export async function listBrands(): Promise<BrandListResult> {
  return apiFetch<BrandListResult>('/v1/brands')
}

/**
 * `brand_id → 名称` 的查表。
 *
 * 任务列表只给 `brand_id`，名称要靠这张表关联 —— 和 counts 里
 * 「competitors 按 brand_id 关联、不许按数组下标」是同一条纪律。
 */
export function brandNameMap(brands: Brand[]): Map<number, string> {
  return new Map(brands.map((b) => [b.id, b.name]))
}
