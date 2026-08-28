'use client'

import { useRouter } from 'next/navigation'
import { useEffect, useState, type FormEvent } from 'react'

import { ApiError } from '@/lib/api/client'
import { useAuth } from '@/lib/auth-context'

import styles from './login.module.css'

/**
 * 登录表单。**没有卡片** —— 风格情报 §5.1 把居中白卡片列为开源味最重的反模式。
 *
 * **失败文案一律「邮箱或密码不正确」**，不区分「用户不存在 / 密码错 / 账号停用」——
 * 后端刻意只回一句话，前端再细分就等于把账号枚举接口做到 UI 上（API.md §2）。
 */
export function LoginForm() {
  const { login, status } = useAuth()
  const router = useRouter()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  // 已登录的人打开 /login 直接送走，别让他再登一次
  useEffect(() => {
    if (status === 'authed') router.replace('/')
  }, [status, router])

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      await login(email.trim(), password)
      router.replace('/')
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setError('邮箱或密码不正确')
      } else if (err instanceof ApiError) {
        setError(err.detail)
      } else {
        // 网络断了、网关挂了 —— 不是凭据问题，说清楚免得用户反复试密码
        setError('无法连接服务器，请稍后重试')
      }
      setBusy(false)
    }
  }

  return (
    <form className={styles.form} onSubmit={onSubmit}>
      <h2 className={styles.formTitle}>进入监测台</h2>

      <div className={styles.field}>
        <label className={styles.label} htmlFor="email">
          工作邮箱
        </label>
        <input
          className={`${styles.input} ${styles.inputMono}`}
          id="email"
          name="email"
          type="email"
          autoComplete="username"
          placeholder="you@company.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          disabled={busy}
          required
        />
      </div>

      <div className={styles.field}>
        <label className={styles.label} htmlFor="password">
          密码
        </label>
        <input
          className={styles.input}
          id="password"
          name="password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          disabled={busy}
          required
        />
      </div>

      <button className={styles.submit} type="submit" disabled={busy}>
        {busy ? '进入中…' : '进入'}
      </button>

      {error ? (
        <p className={styles.error} role="alert">
          {error}
        </p>
      ) : null}

      {/* 没有「注册」也没有「忘记密码」链接 —— 账号由运营在后台建（API.md §3）。
          与其放两个点了没用的链接，不如直接说清楚该找谁。
          文案按风格情报 §5.3：不写「忘记密码？」，写「重置」该找谁。 */}
      <p className={styles.foot}>账号由运营开通。需要重置密码时联系管理员。</p>
    </form>
  )
}
