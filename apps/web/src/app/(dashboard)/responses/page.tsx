import { Suspense } from 'react'

import { Skeleton } from '@/components/ui'

import { ResponsesView } from './ResponsesView'

/**
 * useSearchParams 在静态导出下必须包在 Suspense 里，
 * 否则 `next build` 直接报错 —— 参数只有到客户端才知道。
 */
export default function ResponsesPage() {
  return (
    <Suspense fallback={<Skeleton height={320} />}>
      <ResponsesView />
    </Suspense>
  )
}
