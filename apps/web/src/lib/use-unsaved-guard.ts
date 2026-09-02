'use client'

import { useEffect } from 'react'

/**
 * 有未保存改动时，拦住关闭标签页 / 刷新 / 离开站点。
 *
 * ## 它拦得住什么，拦不住什么
 *
 * `beforeunload` 只在**整页卸载**时触发：关标签页、刷新、跳到站外。
 * 它**拦不住站内跳转** —— 点侧栏、点返回链接、点竞品芯片走开，
 * 未保存的改动照样丢，浏览器不会问。
 *
 * 要连站内也拦住，得去截 Next App Router 的导航，而那套 API 不稳定、
 * 容易和路由打架、也很难测。用户 2026-08-29 拍板：**只拦关闭/刷新**。
 * 这是个明确的取舍，不是漏做 —— 站内那半仍然会静默丢失。
 *
 * ## 浏览器的规矩
 *
 * 现代浏览器**不显示自定义文案**，只弹它自己那句通用的。
 * 所以这里不返回任何字符串去「提示什么内容没保存」—— 那是白写的。
 * `preventDefault()` 是现在的标准写法，`returnValue` 是老浏览器的兜底。
 */
export function useUnsavedGuard(dirty: boolean) {
  useEffect(() => {
    if (!dirty) return

    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault()
      // 老浏览器要这个才弹；新浏览器忽略它的值
      e.returnValue = ''
    }

    window.addEventListener('beforeunload', onBeforeUnload)
    return () => window.removeEventListener('beforeunload', onBeforeUnload)
  }, [dirty])
}
