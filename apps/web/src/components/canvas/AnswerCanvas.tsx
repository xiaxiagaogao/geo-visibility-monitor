'use client'

import { useEffect, useMemo, useRef, useState } from 'react'

import { codePointLength, toCodePoints } from '@/lib/l3/text'

import styles from './canvas.module.css'

/**
 * Answer Canvas —— **全站唯一的签名物件**（风格情报 §6）。
 *
 * 一段模型回答，品牌首次出现被点亮、引用以行内小票浮出、模型名与时间戳
 * 用等宽低对比贴在角落。登录页播这一段；证据页的「一次提及」还是这一段；
 * 将来的报告封面还是这一段。**复用三次以上才叫识别度。**
 *
 * ── 两条不能破的纪律（从 v1 原样带过来）────────────────────────
 *
 * 1. **高亮位置只来自 L1 标注的 `first_offset`**，不做 `indexOf` 兜底。
 *    拿 `matched_term` 自己去正文里找，等于在前端重造一套匹配逻辑，
 *    口径当场分叉；更糟的是找到的那处很可能不是 L1 数的那处，
 *    而页面看起来完全正常 —— 用户会拿一段错的原文去跟客户解释结论。
 *    校验不通过的那一处**不画**，由调用方渲染成告警。
 * 2. **偏移量按码点算，不按 UTF-16 码元。** emoji 与部分汉字是代理对，
 *    用 `String.prototype.slice` 会把它们切成两半（`lib/l3/text`）。
 *
 * ── 打字动效 ──
 *
 * 风格情报 §7.4：「回答流：打字 / 淡入**按 token**，不要整卡弹跳」。
 * 所以这里是**逐段淡入**（按标点切段，近似 token），不是逐字打字机 ——
 * 逐字在中文长文上又慢又假。`prefers-reduced-motion` 直接跳到终态。
 */

export interface CanvasMark {
  /** 在 `text` 里的**码点**下标 */
  offset: number
  /** 命中的字面 */
  term: string
  /** own = 本品（强调色）· rival = 竞品（次级） */
  kind: 'own' | 'rival'
  /** 悬停提示：哪个品牌、靠哪个别名命中 */
  title?: string
}

export interface CanvasCitation {
  index: number
  domain: string
  title?: string | null
  url?: string
}

export function AnswerCanvas({
  text,
  marks,
  citations = [],
  model,
  at,
  /** 播一遍逐段淡入。登录页用；证据页不用（那里要的是可复制的原文） */
  animate = false,
  /** 合成的演示内容 —— 必须标出来，不能让人误当成真实测量结果 */
  synthetic = false,
  className,
}: {
  text: string
  marks: CanvasMark[]
  citations?: CanvasCitation[]
  model?: string
  at?: string
  animate?: boolean
  synthetic?: boolean
  className?: string
}) {
  const segments = useMemo(() => buildSegments(text, marks), [text, marks])

  // 逐段淡入：把正文按标点切成近似 token 的块，逐块显形
  const chunks = useMemo(() => (animate ? countChunks(text) : 0), [animate, text])
  const shown = useReveal(animate ? chunks : 0)

  return (
    <div className={`${styles.canvas} ${className ?? ''}`}>
      {model || at || synthetic ? (
        <div className={styles.meta}>
          {model ? <span className={styles.metaItem}>{model}</span> : null}
          {at ? <span className={styles.metaItem}>{at}</span> : null}
          {synthetic ? <span className={styles.synthetic}>示例内容</span> : null}
        </div>
      ) : null}

      <p className={styles.body}>
        {segments.map((seg, i) =>
          seg.mark ? (
            <mark
              key={i}
              className={seg.mark === 'own' ? styles.own : styles.rival}
              title={seg.title}
              style={animate ? revealStyle(seg.chunk, shown) : undefined}
            >
              {seg.text}
            </mark>
          ) : (
            <span
              key={i}
              style={animate ? revealStyle(seg.chunk, shown) : undefined}
            >
              {seg.text}
            </span>
          ),
        )}
        {animate && shown < chunks ? <span className={styles.caret} aria-hidden="true" /> : null}
      </p>

      {citations.length > 0 ? (
        <div className={styles.cites}>
          {citations.map((c) => (
            <CiteChip key={c.index} cite={c} />
          ))}
        </div>
      ) : null}
    </div>
  )
}

/** 行内引用小票：域名 + 序号。GEO 分析关心的是「哪些站」，所以域名在前。 */
function CiteChip({ cite }: { cite: CanvasCitation }) {
  const inner = (
    <>
      <span className={styles.citeIndex}>{cite.index}</span>
      <span className={styles.citeDomain}>{cite.domain}</span>
    </>
  )
  if (!cite.url) return <span className={styles.cite}>{inner}</span>
  return (
    <a
      className={styles.cite}
      href={cite.url}
      target="_blank"
      rel="noopener noreferrer nofollow"
      title={cite.title ?? cite.url}
    >
      {inner}
    </a>
  )
}

/* ══════════════════════════════════════════════════════════════════
   切片
   ══════════════════════════════════════════════════════════════════ */

interface Segment {
  text: string
  mark?: 'own' | 'rival'
  title?: string
  /** 这一段属于第几个显形块 */
  chunk: number
}

/** 每多少个码点算一「块」—— 近似 token 的粒度 */
const CHUNK = 6

function countChunks(text: string): number {
  return Math.ceil(codePointLength(text) / CHUNK)
}

/**
 * 按标注切片。**不排序也不合并重叠** —— 调用方给的标注已经过校验，
 * 这里多做一层「智能处理」只会让口径变得不可追。
 */
function buildSegments(text: string, marks: CanvasMark[]): Segment[] {
  const cps = toCodePoints(text)
  const sorted = [...marks].sort((a, b) => a.offset - b.offset)
  const out: Segment[] = []
  let cursor = 0

  for (const m of sorted) {
    const len = codePointLength(m.term)
    if (m.offset < cursor || m.offset + len > cps.length) continue // 越界或重叠，跳过
    // **同一条不变量**：切出来的字面必须等于标注说的字面。
    // 对不上就不画 —— 静默画错比空着糟得多（证据页那条规矩，这里也守）。
    if (cps.slice(m.offset, m.offset + len).join('') !== m.term) continue
    if (m.offset > cursor) {
      out.push({ text: cps.slice(cursor, m.offset).join(''), chunk: Math.floor(cursor / CHUNK) })
    }
    out.push({
      text: cps.slice(m.offset, m.offset + len).join(''),
      mark: m.kind,
      title: m.title,
      chunk: Math.floor(m.offset / CHUNK),
    })
    cursor = m.offset + len
  }
  if (cursor < cps.length) {
    out.push({ text: cps.slice(cursor).join(''), chunk: Math.floor(cursor / CHUNK) })
  }
  return out
}

/* ══════════════════════════════════════════════════════════════════
   显形
   ══════════════════════════════════════════════════════════════════ */

function revealStyle(chunk: number, shown: number): React.CSSProperties | undefined {
  return chunk < shown ? undefined : { opacity: 0 }
}

/**
 * 逐块推进。
 *
 * **尊重 `prefers-reduced-motion`：直接跳到终态**，不是放慢 —— 放慢仍然是运动。
 * 也不用 setInterval：标签页切走时 rAF 会自己停，interval 不会。
 */
function useReveal(total: number): number {
  const [shown, setShown] = useState(total > 0 ? 0 : Number.MAX_SAFE_INTEGER)
  const raf = useRef<number | null>(null)

  useEffect(() => {
    if (total <= 0) return
    const reduced =
      typeof window !== 'undefined' &&
      window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    if (reduced) {
      setShown(total)
      return
    }

    setShown(0)
    const start = performance.now()
    // 全程约 2.2 秒 —— 再长就变成让人等的动画，而不是「正在生成」的暗示
    const DURATION = 2200
    const step = (now: number) => {
      const p = Math.min(1, (now - start) / DURATION)
      setShown(Math.ceil(p * total))
      if (p < 1) raf.current = requestAnimationFrame(step)
    }
    raf.current = requestAnimationFrame(step)
    return () => {
      if (raf.current !== null) cancelAnimationFrame(raf.current)
    }
  }, [total])

  return shown
}
