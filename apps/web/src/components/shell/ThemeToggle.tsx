'use client'

import { useEffect, useState } from 'react'

import styles from './shell.module.css'

export const THEME_KEY = 'geo-theme'

/**
 * 浅/深切换。
 *
 * 首屏那一下由 layout 里的内联脚本负责（见 ThemeScript），
 * 这里只管切换与持久化 —— 否则静态导出的 HTML 是浅色，
 * 深色用户会先闪一下白屏。
 */
export function ThemeToggle() {
  const [dark, setDark] = useState(false)

  useEffect(() => {
    setDark(document.documentElement.dataset.theme === 'dark')
  }, [])

  const toggle = () => {
    const next = !dark
    setDark(next)
    document.documentElement.dataset.theme = next ? 'dark' : 'light'
    try {
      localStorage.setItem(THEME_KEY, next ? 'dark' : 'light')
    } catch {
      // 隐私模式下 localStorage 会抛 —— 切换仍然生效，只是不持久
    }
  }

  return (
    <button
      className={styles.iconBtn}
      onClick={toggle}
      aria-label={dark ? '切换到浅色' : '切换到深色'}
      title={dark ? '切换到浅色' : '切换到深色'}
    >
      {dark ? <SunIcon /> : <MoonIcon />}
    </button>
  )
}

/**
 * 在 <head> 里同步执行，避免选了深色的用户看到一帧白屏。
 *
 * **默认浅色**，不跟随系统偏好 —— docs/29 拍板「浅色为主 + 深色可切」，
 * 且视觉稿本身就是照着浅底调的。深色是用户显式选择的结果，不是系统替他选。
 */
export function ThemeScript() {
  const js = `try{document.documentElement.dataset.theme=localStorage.getItem('${THEME_KEY}')==='dark'?'dark':'light'}catch(e){document.documentElement.dataset.theme='light'}`
  return <script dangerouslySetInnerHTML={{ __html: js }} />
}

function SunIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round">
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
    </svg>
  )
}

function MoonIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z" />
    </svg>
  )
}
