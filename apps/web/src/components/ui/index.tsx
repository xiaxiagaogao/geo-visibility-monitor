import type { ReactNode } from 'react'

import { formatFraction, formatRate } from '@/lib/l3/rates'

import styles from './ui.module.css'

/* ── 页头 ──────────────────────────────────────────── */

export function PageHeader({
  crumbs,
  title,
  subtitle,
  actions,
}: {
  crumbs: string[]
  title: string
  subtitle?: ReactNode
  actions?: ReactNode
}) {
  return (
    <div className={styles.pageHead}>
      <div className={styles.crumbs}>
        {crumbs.map((c, i) => (
          <span key={c} className={i === crumbs.length - 1 ? styles.crumbCurrent : undefined}>
            {i > 0 && <span className={styles.crumbSep}>&nbsp;/&nbsp;</span>}
            {c}
          </span>
        ))}
      </div>
      <div className={styles.titleRow}>
        <div>
          <h1 className={styles.title}>{title}</h1>
          {subtitle ? <p className={styles.subtitle}>{subtitle}</p> : null}
        </div>
        {actions ? <div className={styles.actions}>{actions}</div> : null}
      </div>
    </div>
  )
}

export function Button({
  children,
  primary,
  onClick,
  type = 'button',
}: {
  children: ReactNode
  primary?: boolean
  onClick?: () => void
  type?: 'button' | 'submit'
}) {
  return (
    <button
      type={type}
      onClick={onClick}
      className={`${styles.btn} ${primary ? styles.btnPrimary : ''}`}
    >
      {children}
    </button>
  )
}

/* ── Tabs ─────────────────────────────────────────── */

export interface TabItem {
  id: string
  label: string
  count?: number
}

export function Tabs({
  items,
  active,
  onChange,
}: {
  items: TabItem[]
  active: string
  onChange: (id: string) => void
}) {
  return (
    <div className={styles.tabs} role="tablist">
      {items.map((t) => (
        <button
          key={t.id}
          role="tab"
          aria-selected={t.id === active}
          className={`${styles.tab} ${t.id === active ? styles.tabOn : ''}`}
          onClick={() => onChange(t.id)}
        >
          {t.label}
          {t.count !== undefined ? <span className={styles.tabCount}>{t.count}</span> : null}
        </button>
      ))}
    </div>
  )
}

/* ── 筛选行 ───────────────────────────────────────── */

export function FilterBar({ children }: { children: ReactNode }) {
  return <div className={styles.filterBar}>{children}</div>
}

export function SearchInput({ placeholder }: { placeholder: string }) {
  return <input className={styles.input} placeholder={placeholder} aria-label={placeholder} />
}

export function Select({ label, options }: { label: string; options: string[] }) {
  return (
    <select className={styles.select} aria-label={label} defaultValue={options[0]}>
      {options.map((o) => (
        <option key={o}>{o}</option>
      ))}
    </select>
  )
}

/* ── Panel ────────────────────────────────────────── */

export function Panel({
  title,
  subtitle,
  right,
  inset,
  flush,
  children,
}: {
  title?: ReactNode
  subtitle?: ReactNode
  right?: ReactNode
  inset?: boolean
  flush?: boolean
  children?: ReactNode
}) {
  const cls = [styles.panel, inset ? styles.panelInset : '', flush ? styles.panelFlush : '']
    .filter(Boolean)
    .join(' ')

  return (
    <section className={cls}>
      {title || right ? (
        <div className={styles.panelHead}>
          <div>
            {title ? <h2 className={styles.panelTitle}>{title}</h2> : null}
            {subtitle ? <p className={styles.panelSub}>{subtitle}</p> : null}
          </div>
          {right}
        </div>
      ) : (
        subtitle && <p className={styles.panelSub}>{subtitle}</p>
      )}
      {children}
    </section>
  )
}

/* ── Badge ────────────────────────────────────────── */

export type BadgeTone = 'neutral' | 'ok' | 'bad' | 'warn' | 'accent'

const BADGE_CLASS: Record<BadgeTone, string> = {
  neutral: '',
  ok: styles.badgeOk,
  bad: styles.badgeBad,
  warn: styles.badgeWarn,
  accent: styles.badgeAccent,
}

export function Badge({ children, tone = 'neutral' }: { children: ReactNode; tone?: BadgeTone }) {
  return <span className={`${styles.badge} ${BADGE_CLASS[tone]}`}>{children}</span>
}

export function InfoDot({ title }: { title: string }) {
  return (
    <span className={styles.infoDot} title={title} aria-label={title} role="img">
      i
    </span>
  )
}

/* ── Meter ────────────────────────────────────────── */

export function MeterGrid({ children }: { children: ReactNode }) {
  return <div className={styles.meters}>{children}</div>
}

/**
 * 线性 meter —— 不用环形 gauge（dataviz 硬规则，docs/27 §5.2）。
 *
 * props 强制要 `m` 和 `n`：**没有只收 rate 的重载**。
 * 这样「孤零零的百分比」在类型层面就写不出来（docs/27 §5.3）。
 */
export function Meter({
  label,
  info,
  m,
  n,
  tone = 'accent',
  denNote,
}: {
  label: string
  info?: string
  m: number
  n: number
  tone?: 'accent' | 'dim' | 'bad'
  denNote?: string
}) {
  const r = n > 0 ? m / n : null
  const pct = r === null ? 0 : Math.min(1, Math.max(0, r)) * 100

  const valueCls =
    tone === 'accent' ? styles.meterValueAccent : tone === 'bad' ? styles.meterValueBad : ''

  return (
    <div className={styles.meter}>
      <div className={styles.meterLabel}>
        {label}
        {info ? <InfoDot title={info} /> : null}
      </div>
      <div className={`${styles.meterValue} mono ${valueCls}`}>{formatRate(r)}</div>
      <div className={styles.meterTrack}>
        <div
          className={`${styles.meterFill} ${tone === 'dim' ? styles.meterFillDim : ''}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className={`${styles.meterDen} mono`}>{denNote ?? formatFraction(m, n)}</div>
    </div>
  )
}

/**
 * 计数卡：值本身不是比率。
 *
 * **不画轨道** —— 一条满格的轨道摆在「2」下面会被读成「100%」，
 * 而这里的 2 是「10 条提问里有 2 条挂零」。用等高占位保持与 meter 行对齐即可。
 */
export function CountCard({
  label,
  info,
  value,
  note,
  tone = 'dim',
}: {
  label: string
  info?: string
  value: number | string
  note: string
  tone?: 'accent' | 'dim' | 'bad'
}) {
  const valueCls =
    tone === 'accent' ? styles.meterValueAccent : tone === 'bad' ? styles.meterValueBad : ''

  return (
    <div className={styles.meter}>
      <div className={styles.meterLabel}>
        {label}
        {info ? <InfoDot title={info} /> : null}
      </div>
      <div className={`${styles.meterValue} mono ${valueCls}`}>{value}</div>
      <div className={styles.meterTrackless} />
      <div className={styles.meterDen}>{note}</div>
    </div>
  )
}

/* ── 表 / 空态 ────────────────────────────────────── */

export function Table({ children }: { children: ReactNode }) {
  return <table className={styles.table}>{children}</table>
}

export const tableStyles = styles

export function EmptyState({ children }: { children: ReactNode }) {
  return <div className={styles.empty}>{children}</div>
}
