import { NewTaskForm } from './NewTaskForm'

/** 新建任务。写操作，仅超管/运营 —— 客户点不到入口，服务端也会 403。 */
export default function NewTaskPage() {
  return <NewTaskForm />
}
