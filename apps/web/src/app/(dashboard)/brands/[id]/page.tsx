import { notFound } from 'next/navigation'

import { BrandDetailView } from './BrandDetailView'

/** 品牌详情（A2）：基本信息 · 别名 · 竞品 · 删除。提问词是 A3。 */
export default async function BrandPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  const brandId = Number(id)
  // 非法 id 直接 404，不要拿 NaN 去打接口 —— 那会得到 422，
  // 用户看到「加载失败 422」，而真相是这个 URL 根本不合法
  if (!Number.isInteger(brandId) || brandId <= 0) notFound()

  // key 让换品牌时整体重挂 —— 于是视图内部不必在每次重取时把 brand 清成 null。
  // 清成 null 会让三个面板一起卸载：刚点的「已保存」当场消失，还闪一下骨架屏，
  // 用户会以为没保存上。
  return <BrandDetailView key={brandId} brandId={brandId} />
}
