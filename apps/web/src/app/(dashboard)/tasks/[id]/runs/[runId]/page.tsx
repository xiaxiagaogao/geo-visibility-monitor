import { notFound } from 'next/navigation'

import { TaskDetailView } from '../../TaskDetailView'

/**
 * 指定某一次运行。和 `/tasks/[id]` 是同一个视图，只是把 run 钉死。
 *
 * **这是真路由，不是查询参数。** 运营要把某一次运行发给客户，
 * `/tasks/34/runs/128` 和 `?task=34&run=128` 在一个商业产品里不是同一回事。
 */
export default async function RunPage({
  params,
}: {
  params: Promise<{ id: string; runId: string }>
}) {
  const { id, runId } = await params
  const taskIdNum = Number(id)
  const runIdNum = Number(runId)
  if (!Number.isInteger(taskIdNum) || taskIdNum <= 0) notFound()
  if (!Number.isInteger(runIdNum) || runIdNum <= 0) notFound()

  return <TaskDetailView taskId={taskIdNum} runId={runIdNum} />
}
