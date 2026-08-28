'use client'

import { useEffect, useState } from 'react'

import styles from './shell.module.css'

export const THEME_KEY = 'geo-theme'

/**
 * 深/浅切换。
 *
 * **暗色是默认**（视觉立场就是「暗色情报终端」），浅色是显式选择 ——
 * 所以 DOM 上只有选了浅色时才有 `data-theme="light"`，暗色时什么都不写。
 * 上一版方向相反（浅色默认、`data-theme="dark"`），切换逻辑跟着反了过来。
 *
 * 首屏那一下由 layout 里的内联脚本负责（见 ThemeScript），
 * 这里只管切换与持久化。
 */
export function ThemeToggle() {
  const [dark, setDark] = useState(true)

  useEffect(() => {
    setDark(document.documentElement.dataset.theme !== 'light')
  }, [])

  const toggle = () => {
    const next = !dark
    setDark(next)
    if (next) delete document.documentElement.dataset.theme
    else document.documentElement.dataset.theme = 'light'
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
 * 在 <head> 里同步执行，避免选了浅色的用户看到一帧黑屏。
 *
 * **默认暗色**，不跟随系统偏好 —— 视觉立场就是暗色终端，
 * 让系统偏好替用户选会让一半访客看到一个并非为他们设计的版本。
 * 浅色是用户显式点出来的结果。
 */
export function ThemeScript() {
  const js = `try{if(localStorage.getItem('${THEME_KEY}')==='light')document.documentElement.dataset.theme='light'}catch(e){}`
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
