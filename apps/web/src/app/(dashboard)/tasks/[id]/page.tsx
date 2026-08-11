import { notFound } from 'next/navigation'

import { TaskDetailView } from './TaskDetailView'

/**
 * 任务详情 —— **自动落到最新一次运行**。
 *
 * 不重定向到 `/tasks/[id]/runs/[latest]`：那样每次进来 URL 都不一样，
 * 「这个任务」这个概念就没有稳定链接了。运营发「这个任务」发这条，
 * 发「那一次运行」才发带 runId 的那条。
 */
export default async function TaskPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  const taskId = Number(id)
  // `/tasks/abc` 直接 404，不要拿 NaN 去打接口 —— 那会得到一个 422，
  // 用户看到的是「加载失败 422」，而真相是这个 URL 根本不合法。
  if (!Number.isInteger(taskId) || taskId <= 0) notFound()

  return <TaskDetailView taskId={taskId} />
}
