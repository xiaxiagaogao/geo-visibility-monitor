import { EmptyState, Panel, PanelNote } from '@/components/ui'

/**
 * 占位页 —— IA 重构期间的唯一路由。
 *
 * 这里原来是总览看板（KPI 行 + 逐提问 emphasis 条 + 缺口前三 + 品牌对比）。
 * 它连同另外四个页面一起删了，根因不是页面质量，是**整套 IA 的前提错了**：
 * 五个页面全部隐含「系统里只有一个被监测品牌」，`OWN_BRAND_ID` 是模块级常量，
 * 派生数据的七个 selector 全是零参数函数。而后端从第一天起就是多品牌的
 * （`GET /v1/brands` 返回列表，`/v1/counts` 的 brand_id 是必填参数）——
 * 是前端把这个能力压掉了。
 *
 * 保留下来的是与品牌数量无关的部分：设计 token、UI 原语、
 * L3 纯函数（`rate` / `findGaps`）及其 29 个测试、外壳骨架。
 * 想看被删的五个页面：`git show cdb4a97:apps/web/src/app/'(dashboard)'/page.tsx`
 */
export default function PlaceholderPage() {
  return (
    <>
      <Panel title="IA 重构中" subtitle="多品牌与检测任务的信息架构待定">
        <EmptyState>
          <strong style={{ color: 'var(--text-secondary)' }}>页面待重建</strong>
          <span>
            原五页看板按单品牌构建，前提不成立，已移除。
            <br />
            组件库、设计 token 与 L3 纯函数保留在树里，可直接复用。
          </span>
        </EmptyState>
      </Panel>

      <PanelNote>
        重建前要先定的两件事：入口是检测任务列表还是品牌列表；以及后端新增的
        「检测任务」实体长什么样 —— 现有 crawl-job 的粒度是「一条提问的一次采样」，
        35 条样本就是 35 个平铺的 job，中间没有能把它们归成一次检测的东西。
      </PanelNote>
    </>
  )
}
