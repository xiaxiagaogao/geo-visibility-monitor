import { Suspense } from 'react'

import { ResponsesView } from './ResponsesView'

/**
 * useSearchParams 在静态导出下必须包在 Suspense 里，
 * 否则 `next build` 会直接报错 —— 参数只有到客户端才知道。
 */
export default function ResponsesPage() {
  return (
    <Suspense fallback={<div style={{ color: 'var(--muted)' }}>加载中…</div>}>
      <ResponsesView />
    </Suspense>
  )
}
