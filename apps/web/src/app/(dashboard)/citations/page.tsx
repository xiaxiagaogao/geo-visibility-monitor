import { CitationsView } from './CitationsView'

/**
 * 引用榜 —— 「哪些站正在被 AI 引用」。
 *
 * 这一页曾被判定为「不会回来」，理由写在旧侧栏的注释里：citations 全库 0 行，
 * 根因是采集时从未开联网搜索。**那条结论已经被推翻** —— P2-37 打通千问的
 * SSE 流之后，库里现在有 144 条引用、40 个域名。
 *
 * 千问的引用**不在页面 DOM 里**（页面上那块只有站点图标，一条外链都没有），
 * 只存在于流里。公开圈没有第二家从 qianwen.com 抽出过引用
 * （见 `docs/CRAWL-INTEL.md`）—— 这是这个产品唯一同行没有的数据。
 */
export default function CitationsPage() {
  return <CitationsView />
}
