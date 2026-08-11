'use client'

import { useRouter } from 'next/navigation'
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'

import { ApiError } from './api/client'
import { fetchMe, login as apiLogin, logout as apiLogout, type Me } from './api/auth'

type Status = 'loading' | 'authed' | 'anonymous'

interface AuthValue {
  me: Me | null
  status: Status
  login: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthValue | null>(null)

/**
 * 登录状态的唯一来源。
 *
 * 挂载时拉一次 `/v1/auth/me`：200 就拿到身份与 csrf token，401 就是没登录。
 * **401 在这里被当成正常返回处理，不是错误** —— 它是「未登录」这个状态本身。
 *
 * 只有 401 才跳登录。403 是「登录着但没权限」，跳登录会让用户登录成功后
 * 又被弹回来，陷入死循环 —— 那种情况该由页面显示「无权限」。
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null)
  const [status, setStatus] = useState<Status>('loading')

  useEffect(() => {
    let cancelled = false
    fetchMe()
      .then((m) => {
        if (cancelled) return
        setMe(m)
        setStatus('authed')
      })
      .catch((err) => {
        if (cancelled) return
        if (err instanceof ApiError && err.status === 401) {
          setStatus('anonymous')
          return
        }
        // 网络断了、网关 502 —— 这些不是「未登录」，不该把用户踢去登录页
        // （他登了也白登）。当成未认证渲染，但把原因留在控制台。
        console.error('[auth] /v1/auth/me 失败：', err)
        setStatus('anonymous')
      })
    return () => {
      cancelled = true
    }
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    const m = await apiLogin(email, password)
    setMe(m)
    setStatus('authed')
  }, [])

  const logout = useCallback(async () => {
    await apiLogout()
    setMe(null)
    setStatus('anonymous')
  }, [])

  return (
    <AuthContext.Provider value={{ me, status, login, logout }}>{children}</AuthContext.Provider>
  )
}

export function useAuth(): AuthValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth 必须在 <AuthProvider> 内使用')
  return ctx
}

/**
 * 未登录就送去登录页。放在 dashboard 布局里用。
 *
 * 返回 `status`，调用方据此决定渲染骨架还是内容 —— 不要在 loading 阶段
 * 渲染空数据，那会让用户看到一屏「0」然后突然跳变。
 */
export function useRequireAuth(): Status {
  const { status } = useAuth()
  const router = useRouter()

  useEffect(() => {
    if (status === 'anonymous') router.replace('/login')
  }, [status, router])

  return status
}
