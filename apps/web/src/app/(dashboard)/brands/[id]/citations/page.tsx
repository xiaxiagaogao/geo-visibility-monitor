import { notFound } from 'next/navigation'

import { CitationsView } from './CitationsView'

/**
 * 引用榜 —— 「哪些站正在被 AI 引用」。**某一个品牌的**。
 *
 * ## 为什么从顶级导航挪到品牌之下
 *
 * 它一直是按品牌切片的（口径是「这个品牌全部运行的累计」），却和「品牌」
 * 平级挂在侧栏，等于宣称它和「品牌」「任务」是同一类东西。它不是 ——
 * 它是品牌的一个视图。挂在顶级还带来一个具体代价：那一版得自己拉
 * `tasks × brands` 求交集才能知道「谁才是被监测的品牌」，因为
 * `/v1/brands` 返回的 17 个里 16 个是竞品、点进去全是空的。
 * 现在品牌 id 从路由段来，那段推断没有存在的必要了。
 *
 * 当前只有 1 个被监测品牌，所以这个错位一直被数据规模掩盖着 ——
 * 第 2 个客户进来就会暴露。
 *
 * ## 这一页的数据仍然是这个产品的独门
 *
 * 千问的引用**不在页面 DOM 里**（页面上那块只有站点图标，一条外链都没有），
 * 只存在于 SSE 流里。公开圈没有第二家从 qianwen.com 抽出过引用
 * （见 `docs/CRAWL-INTEL.md`）。
 */
export default async function BrandCitationsPage({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const { id } = await params
  const brandId = Number(id)
  // 和品牌详情同一条规矩：非法 id 直接 404，不拿 NaN 去打接口换一个 422
  if (!Number.isInteger(brandId) || brandId <= 0) notFound()

  return <CitationsView key={brandId} brandId={brandId} />
}
