import { CitationsRedirect } from './CitationsRedirect'

/**
 * `/citations` 的旧地址 —— 只做转发，不再有内容。
 *
 * 引用榜已经挪到 `/brands/[id]/citations`（它一直是某个品牌的视图，
 * 挂顶级是 IA 说错了话）。但这个地址在侧栏里挂过一段时间，可能被收藏过，
 * 让它 404 是没必要的死路 —— 转发到默认的被监测品牌就是了。
 */
export default function LegacyCitationsPage() {
  return <CitationsRedirect />
}
