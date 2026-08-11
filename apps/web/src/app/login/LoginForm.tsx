'use client'

import { useRouter } from 'next/navigation'
import { useEffect, useState, type FormEvent } from 'react'

import { ApiError } from '@/lib/api/client'
import { useAuth } from '@/lib/auth-context'

import styles from './login.module.css'

/**
 * 登录表单。
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
    <form className={styles.card} onSubmit={onSubmit}>
      <div className={styles.brand}>
        <div className={styles.mark}>
          <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="11" cy="11" r="7" />
            <path d="M21 21l-4.3-4.3" />
          </svg>
        </div>
        <div>
          <div className={styles.brandName}>GEO 监测台</div>
          <div className={styles.brandSub}>AI 回答可见度监测</div>
        </div>
      </div>

      <p className={styles.lede}>使用账号登录以查看监测数据。</p>

      <label className={styles.label} htmlFor="email">
        邮箱
      </label>
      <input
        className={styles.input}
        id="email"
        name="email"
        type="email"
        autoComplete="username"
        placeholder="you@example.com"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        disabled={busy}
        required
      />

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

      <button className={styles.submit} type="submit" disabled={busy}>
        {busy ? '登录中…' : '登录'}
      </button>

      {error ? (
        <p className={styles.note} role="alert" style={{ color: 'var(--danger)' }}>
          {error}
        </p>
      ) : null}
    </form>
  )
}
