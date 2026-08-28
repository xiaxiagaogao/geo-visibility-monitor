import type { ReactNode } from 'react'

import { formatFraction, formatRate, rate } from '@/lib/l3/rates'

import styles from './kit.module.css'
import { TickScale } from './TickScale'

export { TickScale }
export { Notices, type Notice } from './Notices'
export const kit = styles

/* ══════════════════════════════════════════════════════════════════
   记录纸
   ══════════════════════════════════════════════════════════════════ */

export function Plate({
  title,
  subtitle,
  right,
  flush,
  children,
}: {
  title?: ReactNode
  subtitle?: ReactNode
  right?: ReactNode
  /** 内容自己管内边距（表格、全宽图元） */
  flush?: boolean
  children?: ReactNode
}) {
  return (
    <section className={styles.plate}>
      <div className={flush ? '' : styles.platePad}>
        {title || right ? (
          <div className={styles.plateHead}>
            <div>
              {title ? <h2 className={styles.plateTitle}>{title}</h2> : null}
              {subtitle ? <p className={styles.plateSub}>{subtitle}</p> : null}
            </div>
            {right}
          </div>
        ) : null}
        {children}
      </div>
    </section>
  )
}

/**
 * 页头 —— **每个路由的标题归页面自己**，顶栏只是工具轨。
 *
 * 提成原语是因为 `/tasks` 与 `/citations` 各写了一份，两份 CSS 除了
 * `line-height`（1.7 / 1.75）与 `max-width`（62ch / 68ch）逐字相同 ——
 * 那两个差值没有理由，纯属分头写出来的。而 `/brands`、`/users` 干脆没有页头，
 * 标题塞在面板的 `<h2>` 里 —— 于是全站有三种「这一页叫什么」的表达。
 *
 * `title` 收 ReactNode 而不是 string：任务详情页的标题行跟着一个品牌徽章。
 */
export function PageHead({
  title,
  lede,
  meta,
  action,
}: {
  title: ReactNode
  lede?: ReactNode
  /** 标题下面那行等宽小字（口径、计数），比 lede 更硬 */
  meta?: ReactNode
  /** 右上角的主操作或筛选器 */
  action?: ReactNode
}) {
  return (
    <div className={styles.pageHead}>
      <div className={styles.pageHeadMain}>
        <h1 className={styles.pageTitle}>{title}</h1>
        {lede ? <p className={styles.pageLede}>{lede}</p> : null}
        {meta ? <div className={styles.pageMeta}>{meta}</div> : null}
      </div>
      {action}
    </div>
  )
}

/** 旁注 —— 铅笔写在记录旁边的那种话 */
export function Aside({
  tone = 'plain',
  children,
}: {
  tone?: 'plain' | 'alert' | 'fault'
  children: ReactNode
}) {
  const cls =
    tone === 'alert' ? styles.asideAlert : tone === 'fault' ? styles.asideFault : ''
  return <p className={`${styles.aside} ${cls}`}>{children}</p>
}

/* ══════════════════════════════════════════════════════════════════
   仪器面板
   ── 一块面，几个读数，中间用刻线分隔。
      刻意**不是**四张一样大的卡片 —— 那是类目默认版式，也正是上一版的样子。
   ══════════════════════════════════════════════════════════════════ */

export function Instrument({ children }: { children: ReactNode }) {
  return <div className={styles.panel}>{children}</div>
}

/**
 * 比率读数。
 *
 * props **强制要 `m` 和 `n`**，没有只收算好的 rate 的重载 ——
 * 「孤零零的百分比」在类型层面就写不出来。这条是这个产品可信度的来源，
 * 换了设计系统也不许松（README §3.1）。
 */
export function ReadoutRate({
  label,
  gloss,
  m,
  n,
  denom,
  live,
}: {
  label: string
  gloss?: string
  m: number
  n: number
  /** 覆盖默认的 `m / n` 副文案。仍然必须包含分母 */
  denom?: ReactNode
  /** 这一次运行还没跑完 —— 数字还会动 */
  live?: boolean
}) {
  // null = 不可算（分母 0），0 = 真的是 0 —— 两者显示完全不同
  const r = rate(m, n)
  const zero = r === 0

  return (
    <div className={`${styles.readout} ${live ? styles.readoutLive : ''}`}>
      <div className={styles.readoutLabel}>
        {label}
        {gloss ? <Gloss text={gloss} /> : null}
      </div>
      <div className={styles.readoutValue} data-zero={zero || undefined}>
        {r === null ? '—' : formatRate(r).replace('%', '')}
        {r === null ? null : <span className={styles.readoutUnit}>%</span>}
      </div>
      <TickScale m={m} n={n} />
      <div className={styles.readoutDenom}>{denom ?? formatFraction(m, n)}</div>
    </div>
  )
}

/** 计数读数。值不是比率，所以不带百分号，也不画刻度尺 —— 计数没有分母。 */
export function ReadoutCount({
  label,
  gloss,
  value,
  note,
  alert,
  live,
}: {
  label: string
  gloss?: string
  value: number | string
  note: ReactNode
  alert?: boolean
  live?: boolean
}) {
  return (
    <div className={`${styles.readout} ${live ? styles.readoutLive : ''}`}>
      <div className={styles.readoutLabel}>
        {label}
        {gloss ? <Gloss text={gloss} /> : null}
      </div>
      <div className={styles.readoutValue} data-zero={alert || undefined}>
        {value}
      </div>
      <div className={styles.readoutDenom}>{note}</div>
    </div>
  )
}

/**
 * 降级读数 —— 采到了，但这个维度算不出来。
 *
 * 和「空」必须分开：空是没采到，降级是采到了算不出来。
 * 值用**正文字号**而不是读数字号 —— 一个 44px 的「暂无数据」
 * 会假装自己是一个测量结果。
 */
export function ReadoutBlank({
  label,
  gloss,
  reason,
  note,
}: {
  label: string
  gloss?: string
  reason: string
  note: ReactNode
}) {
  return (
    <div className={styles.readout}>
      <div className={styles.readoutLabel}>
        {label}
        {gloss ? <Gloss text={gloss} /> : null}
      </div>
      <div className={styles.readoutMuted}>{reason}</div>
      <div className={styles.readoutDenom}>{note}</div>
    </div>
  )
}

/* ══════════════════════════════════════════════════════════════════
   记号
   ══════════════════════════════════════════════════════════════════ */

export type MarkTone = 'plain' | 'ok' | 'warn' | 'fault' | 'own' | 'void'

const MARK_TONE: Record<MarkTone, string> = {
  plain: '',
  ok: styles.markOk,
  warn: styles.markWarn,
  fault: styles.markFault,
  own: styles.markOwn,
  // 「我们不知道」在纸上是一段没有笔迹的地方，不是一个更淡的实心块
  void: styles.markVoid,
}

/**
 * 把 `lib/l3` 那边的色调名映射到这一套记号。
 *
 * L3 的 `Tone`（run-status / search-used 都在用）是照上一套原语的
 * `BadgeTone` 定的。**不去改 L3** —— 那一层有 238 条测试钉着，
 * 为了换个设计系统去动纯函数的公开契约，是拿口径层的稳定性换表现层的方便。
 * 映射放在表现层，这里就是那条边界。
 */
export function markTone(tone: 'ok' | 'warning' | 'danger' | 'neutral' | 'accent'): MarkTone {
  if (tone === 'ok') return 'ok'
  if (tone === 'warning') return 'warn'
  if (tone === 'danger') return 'fault'
  if (tone === 'accent') return 'own'
  return 'plain'
}

export function Mark({
  children,
  tone = 'plain',
  dot,
}: {
  children: ReactNode
  tone?: MarkTone
  dot?: boolean
}) {
  return (
    <span className={`${styles.mark} ${MARK_TONE[tone]}`}>
      {dot ? <span className={styles.dot} /> : null}
      {children}
    </span>
  )
}

/** 口径提示。用 button 而不是 span：键盘要够得着。 */
export function Gloss({ text }: { text: string }) {
  return (
    <button type="button" className={styles.gloss} title={text} aria-label={`口径：${text}`}>
      i
    </button>
  )
}

/* ══════════════════════════════════════════════════════════════════
   控件
   ══════════════════════════════════════════════════════════════════ */

export function Button({
  children,
  primary,
  onClick,
  type = 'button',
  disabled,
  title,
}: {
  children: ReactNode
  primary?: boolean
  onClick?: () => void
  type?: 'button' | 'submit'
  /**
   * 请求在飞的时候必须传 —— 只把文案改成「发起中…」挡不住第二次点击，
   * 而「立即运行」点两次就是两个 run、两批 job、两份额度，且撤不回来。
   */
  disabled?: boolean
  title?: string
}) {
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={`${styles.btn} ${primary ? styles.btnPrimary : ''}`}
    >
      {children}
    </button>
  )
}

/** 行内输入。整页居中的登录卡片有自己的一份，两者刻意不共用。 */
export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={`${styles.input} ${props.className ?? ''}`} />
}

export function Select(props: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...props} className={`${styles.select} ${props.className ?? ''}`} />
}

export function Table({ children }: { children: ReactNode }) {
  return <table className={styles.table}>{children}</table>
}

/* ══════════════════════════════════════════════════════════════════
   三态
   ══════════════════════════════════════════════════════════════════ */

export function Pending({ height = 16, width = '100%' }: { height?: number; width?: string }) {
  return <div className={styles.pending} style={{ height, width }} />
}

export function Blank({ lead, children }: { lead: ReactNode; children?: ReactNode }) {
  return (
    <div className={styles.blank}>
      <div className={styles.blankLead}>{lead}</div>
      {children ? <div className={styles.blankBody}>{children}</div> : null}
    </div>
  )
}

export function Fault({
  status,
  code,
  message,
  onRetry,
}: {
  status: number
  code?: string
  message: string
  onRetry?: () => void
}) {
  return (
    <div className={styles.fault} role="alert">
      <div style={{ flex: 1 }}>
        <div className={styles.faultLead}>没读到这段记录</div>
        <div className={styles.faultDetail}>
          {status || '—'}
          {code ? ` · ${code}` : ''} · {message}
        </div>
      </div>
      {onRetry ? <Button onClick={onRetry}>重试</Button> : null}
    </div>
  )
}

/* ══════════════════════════════════════════════════════════════════
   记号法图例
   ── 图上出现的每一种记号在这里都有定义。
      上一版这套图例只存在于命中矩阵底下一行。
   ══════════════════════════════════════════════════════════════════ */

export interface NotationEntry {
  /** 色块的背景；给 'void' 画成虚线空心 */
  swatch: string | 'void' | 'zero'
  label: string
}

export function Notation({ entries, note }: { entries: NotationEntry[]; note?: ReactNode }) {
  return (
    <div className={styles.notation}>
      {entries.map((e) => (
        <span key={e.label} className={styles.notationItem}>
          <span
            className={styles.notationKey}
            style={
              e.swatch === 'void'
                ? { border: '1px dashed var(--border-strong)' }
                : e.swatch === 'zero'
                  ? { boxShadow: 'inset 0 0 0 1.5px var(--tick-zero)' }
                  : { background: e.swatch }
            }
          />
          {e.label}
        </span>
      ))}
      {note ? <span style={{ marginLeft: 'auto', color: 'var(--text-3)' }}>{note}</span> : null}
    </div>
  )
}
