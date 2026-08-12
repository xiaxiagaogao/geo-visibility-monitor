/**
 * 品牌。字段以 `docs/API.md` §6 为准。
 */
import type { Brand } from '../types'
import { apiFetch } from './client'

export interface BrandListResult {
  items: Brand[]
  total: number
}

/**
 * 品牌列表。
 *
 * `workspaceId` 对**客户身份无效** —— 服务端强制收敛到他自己的 workspace
 * （`visible_workspace_id`），传什么都会被覆盖。这个参数是给超管/运营
 * 筛选用的，不是权限边界。
 */
export async function listBrands(
  params: { workspaceId?: number } = {},
): Promise<BrandListResult> {
  return apiFetch<BrandListResult>('/v1/brands', {
    query: { workspace_id: params.workspaceId },
  })
}

export async function getBrand(brandId: number): Promise<Brand> {
  return apiFetch<Brand>(`/v1/brands/${brandId}`)
}

export interface BrandCreateInput {
  name: string
  name_en?: string | null
  industry?: string | null
  /**
   * **建完就改不了了。** `BrandUpdate` 里没有这个字段 —— 品牌不能换 workspace，
   * 所以它决定了「哪些客户账号能看到这个品牌」，且是一次性决定。
   */
  workspace_id: number
  aliases?: string[]
}

export async function createBrand(input: BrandCreateInput): Promise<Brand> {
  return apiFetch<Brand>('/v1/brands', { method: 'POST', body: input })
}

/** 改基本信息。**不含 `workspace_id`**，后端也不收 —— 品牌过不了户。 */
export async function updateBrand(
  brandId: number,
  input: { name?: string; name_en?: string | null; industry?: string | null },
): Promise<Brand> {
  return apiFetch<Brand>(`/v1/brands/${brandId}`, { method: 'PATCH', body: input })
}

/** 删品牌。**级联删除**它的提问词、竞品关系与相关标注，调用方必须先确认。 */
export async function deleteBrand(brandId: number): Promise<void> {
  await apiFetch(`/v1/brands/${brandId}`, { method: 'DELETE' })
}

/**
 * 替换别名。**整体替换，不是追加**（API.md §6）——
 * 传进来的列表就是保存后的全部，没带上的会被删掉。
 *
 * 所以调用方必须先读全量、在全量上编辑、再整份提交。
 * 只提交新增的那一条，会把其余别名全删掉，而接口返回 200。
 */
export async function replaceAliases(brandId: number, aliases: string[]): Promise<Brand> {
  return apiFetch<Brand>(`/v1/brands/${brandId}/aliases`, {
    method: 'PUT',
    body: { aliases },
  })
}

/**
 * 替换竞品集。**整体替换**，同上。
 *
 * ⚠️ 这个操作会影响**未来**的 run：竞品集是发起 run 时冻结进快照的，
 * 改它不会回头改写历史运行（那正是 `run_competitors` 存在的理由），
 * 但下一次运行的缺口清单与失分量会按新集合算。
 */
export async function replaceCompetitors(
  brandId: number,
  competitorIds: number[],
): Promise<Brand> {
  return apiFetch<Brand>(`/v1/brands/${brandId}/competitors`, {
    method: 'PUT',
    body: { competitor_ids: competitorIds },
  })
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
