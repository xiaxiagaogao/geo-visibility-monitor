import type { Metadata } from 'next'
import type { ReactNode } from 'react'

import { ThemeScript } from '@/components/shell/ThemeToggle'
import { AuthProvider } from '@/lib/auth-context'
import '@/styles/globals.css'

const DIRECTION_CONTRACT = `<!--
GEO 监测台 · 方向契约 (impeccable seed e13eab31 · direction · operate · code-led)

THESIS: 这不是仪表盘，是一份记录。拒绝「四张一样的 KPI 卡 + 折线图」那套
  类目默认排布 —— 那正是它上一版的样子。
OWN-WORLD: 熏烟纸地震图。浅色是冲印正片、深色是熏烟原片，同一份记录的两面。
  中性灰纸 + 烟墨，全站只有两支铅笔：蓝（本品/主操作）红（告警/挂零）。
  分钟刻线是纸的纹理；四角近乎切齐（圆角 1–3px）；数字戴 Martian Mono，
  中文展示字是得意黑，两款都自托管。
STORY: 看的人先看见一段时间上的记录，再看见这一次的读数由多大的分母撑着，
  最后能顺着标注回到原文的第 N 个字符。他带走的是一份缺口清单。
FIRST VIEWPORT: 顶部一条贯穿整宽的时间纸带（12 次 run，本品实线、竞品淡线，
  采集条件变过处画断口并写明「口径变了，两段不可直接比」）；纸带下方是**一块**
  仪器面板（不是四张卡），四个读数以刻线分隔，每个读数下面是一条按分母刻度的
  标尺 —— 18 格和 12 格一眼不一样长。主操作「立即运行」在面板右上。
FORM: 自选 grounded 列表第 6 位「纸带记录仪」，由骰子分配，用户确认。seed e13eab31。
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish
  review, the verdict, DESIGN.md, and every shipping raster carrying its provenance.
-->`

export const metadata: Metadata = {
  title: 'GEO 监测台',
  description: '品牌在 AI 回答中的可见度监测 —— 每个数字都能下钻到原文',
}

/**
 * 根布局：html/body、全局样式、主题脚本，以及**全站唯一的 AuthProvider**。
 *
 * Provider 放这里而不是各路由组里：放下面的话登录页和 dashboard 各有一个，
 * 状态不共享 —— 登录成功跳转后会再拉一次 /me，且两边对「我是谁」的认知
 * 可能短暂不一致。
 *
 * Sidebar + Topbar 那层壳仍在 (dashboard) 路由组里 —— 登录页不该套壳。
 */
export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="zh-CN" data-theme="light" suppressHydrationWarning>
      <head>
        <ThemeScript />
      </head>
      <body>
        {/* 方向契约。它必须活到生产构建之后 —— 一份 grep 不到的契约没人能审。
            React 渲染不出裸注释，所以套一个不可见的容器。 */}
        <div hidden dangerouslySetInnerHTML={{ __html: DIRECTION_CONTRACT }} />
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  )
}
