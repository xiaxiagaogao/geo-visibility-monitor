import type { Brand, Task } from '@/lib/types'

/**
 * 品牌在这个产品里扮演两种完全不同的角色，而 `Brand` 表上**没有字段区分它们**。
 *
 * ## 为什么必须分
 *
 * 实测生产库：17 个品牌里只有 **2 个**是监测对象（安踏、土巴兔），
 * 其余 15 个是作为对照存在的竞品。把它们平级列在一张表里的后果不是难看：
 *
 *   · 竞品列 15/17 是空的
 *   · 引用榜为了知道「谁才是主语」，得在客户端拉 tasks 和 brands 求交集
 *   · 点进任何一个竞品，看到的是一整套配置页，而那个品牌永远不会被跑
 *
 * ## 判据（**注意方向**）
 *
 * 直觉写法是「有任务或有竞品集的才是监测对象」—— **那是错的**。
 * 用户点「新建品牌 +」建出来的品牌，此刻没任务、没竞品集、也没人引用它，
 * 按那个判据会被判成非监测对象、从列表里消失 —— 也就是**刚建完就找不到了**。
 *
 * 所以判据反过来写，默认属于列表，只把明确的参照排除掉：
 *
 *   参照 = 被别人引为竞品 **且** 自己既没有任务、也没有竞品集
 *   其余一律是监测对象（含刚建出来、还没配任何东西的）
 *
 * 这样「新建」这条路径天然是对的，不需要额外兜底。
 */

export type BrandRole = 'monitored' | 'reference'

export interface ClassifiedBrand {
  brand: Brand
  role: BrandRole
  /** 有几个任务在盯它。0 表示配好了但还没建任务 */
  taskCount: number
  /** 它被哪些监测品牌引为竞品 —— 参照品牌靠这个才找得回去 */
  referencedBy: number[]
}

export interface BrandRoster {
  monitored: ClassifiedBrand[]
  reference: ClassifiedBrand[]
}

/**
 * 把品牌分成「监测对象」与「参照」。
 *
 * `tasks` 只用到 `brand_id`；传一个空数组也是合法的（还没有任何任务时，
 * 分类退化成「有竞品集的 + 没被引用的」，仍然不会把新建品牌弄丢）。
 */
export function classifyBrands(brands: Brand[], tasks: Pick<Task, 'brand_id'>[]): BrandRoster {
  const taskCounts = new Map<number, number>()
  for (const t of tasks) {
    taskCounts.set(t.brand_id, (taskCounts.get(t.brand_id) ?? 0) + 1)
  }

  // 谁被谁引为竞品。**用 id 关联，不能拿数组下标当身份。**
  const referencedBy = new Map<number, number[]>()
  for (const b of brands) {
    for (const cid of b.competitor_ids) {
      // 自引是脏数据，忽略 —— 否则一个品牌会把自己判成参照
      if (cid === b.id) continue
      const list = referencedBy.get(cid) ?? []
      list.push(b.id)
      referencedBy.set(cid, list)
    }
  }

  const monitored: ClassifiedBrand[] = []
  const reference: ClassifiedBrand[] = []

  for (const brand of brands) {
    const taskCount = taskCounts.get(brand.id) ?? 0
    const refs = referencedBy.get(brand.id) ?? []
    const isReference = refs.length > 0 && taskCount === 0 && brand.competitor_ids.length === 0
    const entry: ClassifiedBrand = {
      brand,
      role: isReference ? 'reference' : 'monitored',
      taskCount,
      referencedBy: refs,
    }
    ;(isReference ? reference : monitored).push(entry)
  }

  return { monitored, reference }
}

/**
 * 某个监测品牌的竞品，按它自己 `competitor_ids` 的顺序返回。
 *
 * **顺序的唯一依据是 `competitor_ids` 本身**（见 `types.ts` 的注释）——
 * 不许按名字排、也不许拿 counts 里的数组下标当顺序。
 * 找不到的 id 会被跳过而不是塞一个占位：竞品被删掉之后 id 还留在数组里是
 * 可能的，画一个「#41」出来只会让人以为是个真品牌。
 */
export function competitorsOf(brand: Brand, all: Brand[]): Brand[] {
  const byId = new Map(all.map((b) => [b.id, b]))
  const out: Brand[] = []
  for (const cid of brand.competitor_ids) {
    const found = byId.get(cid)
    if (found) out.push(found)
  }
  return out
}

/**
 * 引用榜、以及任何「按被监测品牌看」的视图，默认该落在哪个品牌上。
 *
 * 有任务的优先（引用只可能来自跑过的运行），其次是配了竞品集的。
 * 都没有就返回 null —— 调用方必须自己处理空态，不能瞎选一个。
 */
export function defaultMonitoredBrandId(roster: BrandRoster): number | null {
  const withTask = roster.monitored.filter((m) => m.taskCount > 0)
  if (withTask.length > 0) return withTask[0].brand.id
  return roster.monitored[0]?.brand.id ?? null
}
