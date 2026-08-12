'use client'

import { useCallback, useEffect, useState, type FormEvent } from 'react'

import runs from '@/components/runs/runs.module.css'
import {
  Badge,
  Button,
  EmptyState,
  ErrorState,
  Panel,
  PanelNote,
  Skeleton,
  Table,
  ui,
  type BadgeTone,
} from '@/components/ui'
import { isSuperadmin, type Role } from '@/lib/api/auth'
import { ApiError } from '@/lib/api/client'
import { createUser, deleteUser, listUsers, updateUser, type User } from '@/lib/api/users'
import { useAuth } from '@/lib/auth-context'
import {
  ASSIGNABLE_ROLES,
  canDeleteUser,
  needsWorkspace,
  roleLabel,
  workspaceForRole,
} from '@/lib/l3/users'

const ROLE_TONE: Record<string, BadgeTone> = {
  superadmin: 'danger',
  operator: 'accent',
  client: 'neutral',
}

/**
 * 用户管理（A4）。**整组接口只有超管能用**（后端 `require_superadmin`）。
 *
 * 三条不显然的语义做进了界面：
 *
 *   1. **只有客户有 workspace。** 超管/运营的会被后端强制置 null，
 *      所以选了这两个角色时输入框直接消失 —— 留着它，填了不生效而界面
 *      看起来像生效了。
 *   2. **改密 / 停用会吊销该用户全部会话。** 否则旧会话继续有效，等于没改。
 *      这是用户看不见的副作用，操作前先说。
 *   3. **不能删自己。** 超管删光就没人能管用户了，只能进库改。
 */
export function UsersView() {
  const { me } = useAuth()
  const [users, setUsers] = useState<User[] | null>(null)
  const [error, setError] = useState<Error | null>(null)
  const [reloadKey, setReloadKey] = useState(0)

  const reload = useCallback(() => setReloadKey((k) => k + 1), [])

  useEffect(() => {
    let alive = true
    setError(null)
    listUsers()
      .then((r) => {
        if (alive) setUsers(r.items)
      })
      .catch((e: unknown) => {
        if (alive) setError(e instanceof Error ? e : new Error(String(e)))
      })
    return () => {
      alive = false
    }
  }, [reloadKey])

  // 前端按角色隐藏只是体验，服务端的 require_superadmin 才是边界 ——
  // 但运营点进来会拿到一个 403，说清楚比让他看「加载失败 403」强
  if (!isSuperadmin(me)) {
    return (
      <Panel title="用户管理">
        <EmptyState>
          <strong style={{ color: 'var(--text-secondary)' }}>只有超级管理员能管理用户</strong>
          <span>这不是界面限制 —— 接口本身就只对超管开放。</span>
        </EmptyState>
      </Panel>
    )
  }

  if (error) {
    return (
      <ErrorState
        status={error instanceof ApiError ? error.status : 0}
        message={error instanceof ApiError ? error.detail : '加载失败'}
        onRetry={reload}
      />
    )
  }

  if (users === null) {
    return (
      <div style={{ display: 'grid', gap: 8 }}>
        <Skeleton height={20} />
        <Skeleton height={20} />
      </div>
    )
  }

  return (
    <div className={runs.panelStack}>
      <Panel
        title="用户"
        subtitle="客户只能看到自己 workspace 下的品牌；超管与运营看全部"
        right={
          <span style={{ fontSize: 'var(--fs-xs)', color: 'var(--text-tertiary)' }}>
            共 {users.length} 个
          </span>
        }
      >
        <Table>
          <thead>
            <tr>
              <th>邮箱</th>
              <th>角色</th>
              <th>workspace</th>
              <th>状态</th>
              <th>最近登录</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <UserRow
                key={u.id}
                user={u}
                myUserId={me?.user_id ?? null}
                onChanged={reload}
              />
            ))}
          </tbody>
        </Table>
      </Panel>

      <CreateUserPanel onCreated={reload} />
    </div>
  )
}

/* ══════ 一行 ══════ */

function UserRow({
  user,
  myUserId,
  onChanged,
}: {
  user: User
  myUserId: number | null
  onChanged: () => void
}) {
  const [busy, setBusy] = useState(false)
  const [armed, setArmed] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const isSelf = myUserId !== null && myUserId === user.id
  const deletable = canDeleteUser(myUserId, user.id)

  async function run(fn: () => Promise<unknown>) {
    setBusy(true)
    setErr(null)
    try {
      await fn()
      onChanged()
    } catch (e) {
      setErr(e instanceof ApiError ? e.detail : '操作失败')
    } finally {
      setBusy(false)
    }
  }

  return (
    <tr>
      <td>
        {user.email}
        {isSelf ? (
          <span style={{ marginLeft: 6 }}>
            <Badge tone="accent">你自己</Badge>
          </span>
        ) : null}
        {err ? (
          <div role="alert" style={{ color: 'var(--danger)', fontSize: 'var(--fs-xs)' }}>
            {err}
          </div>
        ) : null}
        {armed ? (
          <div className={ui.deleteWarn} role="alert">
            <strong style={{ color: 'var(--danger)' }}>删除「{user.email}」？</strong>
            他的全部会话会一起失效，无法撤销。
            <br />
            只是想暂时禁止他登录 → 点<strong>停用</strong>，账号和历史都留着。
          </div>
        ) : null}
      </td>

      <td>
        <Badge tone={ROLE_TONE[user.role] ?? 'neutral'}>{roleLabel(user.role)}</Badge>
      </td>

      <td className={ui.numeric}>
        {/* 超管/运营是 null，显示 — 而不是空白：空白看起来像没加载出来 */}
        {user.workspace_id ?? '—'}
      </td>

      <td>
        {user.is_active ? <Badge tone="ok">启用中</Badge> : <Badge tone="warning">已停用</Badge>}
      </td>

      <td className={ui.numeric} style={{ fontSize: 'var(--fs-xs)', color: 'var(--text-tertiary)' }}>
        {user.last_login_at ? user.last_login_at.slice(0, 16).replace('T', ' ') : '从未登录'}
      </td>

      <td>
        <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
          {armed ? (
            <>
              <Button primary onClick={() => run(() => deleteUser(user.id))} disabled={busy}>
                {busy ? '删除中…' : '确认删除'}
              </Button>
              <Button onClick={() => setArmed(false)} disabled={busy}>
                取消
              </Button>
            </>
          ) : (
            <>
              {/* 停用会吊销他全部会话 —— 后端 revoke_all_sessions，
                  否则旧会话继续有效，等于没停 */}
              <Button
                onClick={() => run(() => updateUser(user.id, { is_active: !user.is_active }))}
                disabled={busy || isSelf}
              >
                {user.is_active ? '停用' : '启用'}
              </Button>
              <Button onClick={() => setArmed(true)} disabled={busy || !deletable}>
                删除
              </Button>
            </>
          )}
        </div>
        {isSelf ? (
          <div
            style={{
              fontSize: 'var(--fs-2xs)',
              color: 'var(--text-tertiary)',
              textAlign: 'right',
              marginTop: 2,
            }}
          >
            不能停用或删除自己
          </div>
        ) : null}
      </td>
    </tr>
  )
}

/* ══════ 建用户 ══════ */

function CreateUserPanel({ onCreated }: { onCreated: () => void }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState<Role>('client')
  const [workspaceId, setWorkspaceId] = useState<number | ''>('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setErr(null)

    // 按角色归一化 —— 与后端 _validate_role_workspace 同口径。
    // undefined = 客户没给 workspace，当场拦下，不必等一个 400
    const ws = workspaceForRole(role, workspaceId === '' ? null : workspaceId)
    if (ws === undefined) {
      setErr('客户必须指定 workspace_id，否则他登录进来什么都看不到')
      return
    }

    setBusy(true)
    try {
      await createUser({ email: email.trim().toLowerCase(), password, role, workspace_id: ws })
      setEmail('')
      setPassword('')
      setWorkspaceId('')
      onCreated()
    } catch (e2) {
      // 409 单独给一句话 —— 只说「创建失败」的话，超管会以为是接口坏了
      setErr(
        e2 instanceof ApiError && e2.status === 409
          ? '这个邮箱已经有账号了'
          : e2 instanceof ApiError
            ? e2.detail
            : '创建失败，请稍后重试',
      )
    } finally {
      setBusy(false)
    }
  }

  return (
    <Panel title="新建用户">
      <form onSubmit={onSubmit} className={ui.formGrid}>
        <label className={ui.field}>
          <span className={ui.fieldLabel}>邮箱</span>
          <input
            className={ui.input}
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            disabled={busy}
            required
            autoComplete="off"
          />
        </label>

        <label className={ui.field}>
          <span className={ui.fieldLabel}>初始密码</span>
          <input
            className={ui.input}
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            disabled={busy}
            required
            autoComplete="new-password"
          />
          <span style={{ fontSize: 'var(--fs-xs)', color: 'var(--text-tertiary)' }}>
            长度不够的话后端会拒绝并告诉你最短几位 —— 这里不复制那个数字，
            免得两边对不上。
          </span>
        </label>

        <label className={ui.field}>
          <span className={ui.fieldLabel}>角色</span>
          <select
            className={ui.input}
            value={role}
            onChange={(e) => setRole(e.target.value as Role)}
            disabled={busy}
          >
            {ASSIGNABLE_ROLES.map((r) => (
              <option key={r} value={r}>
                {roleLabel(r)}
              </option>
            ))}
          </select>
        </label>

        {/* 只有客户显示这一项。超管/运营的 workspace 会被后端置 null ——
            给他们留着输入框，填了不生效而界面看起来像生效了 */}
        {needsWorkspace(role) ? (
          <label className={ui.field}>
            <span className={ui.fieldLabel}>workspace_id</span>
            <input
              className={ui.input}
              type="number"
              min={1}
              value={workspaceId}
              onChange={(e) => setWorkspaceId(e.target.value === '' ? '' : Number(e.target.value))}
              disabled={busy}
              required
              style={{ maxWidth: 160 }}
            />
            <span style={{ fontSize: 'var(--fs-xs)', color: 'var(--text-tertiary)' }}>
              他只能看到这个 workspace 下的品牌。填错的话他登录进来会看到别人的数据，
              或者什么都看不到 —— 在品牌页能查到每个品牌属于哪个 workspace。
            </span>
          </label>
        ) : (
          <PanelNote>
            {roleLabel(role)}看<strong>全部</strong> workspace 的数据，
            所以没有 workspace 这一项 —— 后端会把它置空。
          </PanelNote>
        )}

        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <Button type="submit" primary disabled={busy}>
            {busy ? '创建中…' : '创建用户'}
          </Button>
        </div>

        {err ? (
          <p role="alert" style={{ color: 'var(--danger)', fontSize: 'var(--fs-xs)' }}>
            {err}
          </p>
        ) : null}
      </form>
    </Panel>
  )
}
