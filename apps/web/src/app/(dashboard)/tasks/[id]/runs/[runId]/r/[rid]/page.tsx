import { notFound } from 'next/navigation'

import { EvidenceView } from './EvidenceView'

/**
 * 单条回答证据（A7）。
 *
 * **证据是真路由，不是查询参数。** 运营要把某一条证据发给客户，
 * `/tasks/34/runs/128/r/29` 和 `?id=34&run=128&rid=29` 在一个商业产品里
 * 不是同一回事 —— 前者能收藏、能进邮件、能当工单附件。
 */
export default async function EvidencePage({
  params,
}: {
  params: Promise<{ id: string; runId: string; rid: string }>
}) {
  const { id, runId, rid } = await params
  const taskId = Number(id)
  const runIdNum = Number(runId)
  const responseId = Number(rid)
  // 非法 id 直接 404，不要拿 NaN 去打接口 —— 那会得到 422，
  // 用户看到「加载失败 422」，而真相是这个 URL 根本不合法
  for (const n of [taskId, runIdNum, responseId]) {
    if (!Number.isInteger(n) || n <= 0) notFound()
  }

  return <EvidenceView taskId={taskId} runId={runIdNum} responseId={responseId} />
}
