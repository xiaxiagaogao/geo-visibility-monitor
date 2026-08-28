import type { Metadata } from 'next'
import type { ReactNode } from 'react'

import { ThemeScript } from '@/components/shell/ThemeToggle'
import { AuthProvider } from '@/lib/auth-context'
import '@/styles/globals.css'

const DIRECTION_CONTRACT = `<!--
GEO 监测台 · 方向契约 v2（用户 brief 钉死，见 GEO-前端风格情报.md）

THESIS: 暗色情报终端。一种强调色。回答流是唯一装饰。登录和监测台共用同一个
  签名物件。拒绝「居中登录卡 + 圆角白卡片栅格 + 亮蓝主按钮」那张开源后台脸 ——
  那正是 v0 的样子。
OWN-WORLD: 画布近黑且偏冷 #08090B（明确不用 #0F172A）；表面靠底色差 4–8% 分层，
  边框白 8%，几乎看不见；强调色只给数据、高亮与状态，**主 CTA 是白底黑字**；
  半径 4–6px；Geist / Geist Mono / 思源 600 子集三种声音；紧追踪标题。
STORY: 看的人先看见一段真实的 AI 回答里自己的品牌被点亮，再看见这次测量的
  分母有多大，最后能顺着标注回到原文的第 N 个字符。他带走一份缺口清单。
FIRST VIEWPORT: 登录页左右劈开 —— 左侧是 Answer Canvas（一段正在生成的回答，
  品牌高亮、引用小票浮出），右侧是表单，无卡片。监测台首屏是四个真实读数
  （有效样本/提及率/首位提及率/覆盖缺口，**没有 Sentiment：本产品恒 NULL**）
  加单色面积图与竞品表。
FORM: 用户 brief 指定，非骰子分配 —— brief 优先于 roll。路线 A 做壳、B 做核心、
  C 只留给报告封面。替换 v1（熏烟纸地震图，seed e13eab31）。
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
  // 暗色是默认，所以 html 上不带 data-theme；选了浅色才由 ThemeScript 写上
  return (
    <html lang="zh-CN" suppressHydrationWarning>
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
