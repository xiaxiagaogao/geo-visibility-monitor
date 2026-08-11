import { HomeRedirect } from './HomeRedirect'

/**
 * 首页 —— 只负责按角色分流，自己不渲染内容。
 *
 * 这里原来是单品牌总览看板，随那套 IA 一起删了；
 * 想看：`git show cdb4a97:apps/web/src/app/'(dashboard)'/page.tsx`
 */
export default function HomePage() {
  return <HomeRedirect />
}
