import type { ReactNode } from 'react'

import { formatFraction, formatRate, rate } from '@/lib/l3/rates'

import styles from './ui.module.css'

export const ui = styles

/* 页标题在 Topbar 里（照搬 GeoMonitor 的做法），页面本身不再重复一遍标题 */

export function Button({
  children,
  primary,
  onClick,
  type = 'button',
  disabled,
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
}) {
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`${styles.btn} ${primary ? styles.btnPrimary : ''}`}
    >
      {children}
    </button>
  )
}

/* ══════ Panel ══════ */

export function Panel({
  title,
  subtitle,
  right,
  children,
}: {
  title?: ReactNode
  subtitle?: ReactNode
  right?: ReactNode
  children?: ReactNode
}) {
  return (
    <section className={styles.panel}>
      {title || right ? (
        <div className={styles.panelHead}>
          <div>
            {title ? <h2 className={styles.panelTitle}>{title}</h2> : null}
            {subtitle ? <p className={styles.panelSub}>{subtitle}</p> : null}
          </div>
          {right}
        </div>
      ) : null}
      {children}
    </section>
  )
}

export function PanelNote({ children }: { children: ReactNode }) {
  return <p className={styles.panelNote}>{children}</p>
}

/* ══════ KPI ══════ */

export function KpiGrid({ children }: { children: ReactNode }) {
  return <div className={styles.kpiGrid}>{children}</div>
}

/**
 * 比率型 KPI。
 *
 * props **强制要 `m` 和 `n`**，没有只收 rate 的重载 ——
 * 这样「孤零零的百分比」在类型层面就写不出来 —— 凡显示比率必须同时显示 m / n
 * （API.md §4.2 第 4 条），这是这个产品可信度的来源。
 */
export function KpiRate({
  label,
  info,
  m,
  n,
  denomLabel,
  alert,
}: {
  label: string
  info?: string
  m: number
  n: number
  denomLabel?: string
  alert?: boolean
}) {
  // null = 不可算（分母为 0），0 = 真的是 0 —— 两者显示完全不同
  const r = rate(m, n)
  return (
    <div className={`${styles.kpi} ${alert ? styles.kpiAlert : ''}`}>
      <div className={styles.kpiLabel}>
        {label}
        {info ? <InfoDot title={info} /> : null}
      </div>
      <div className={`${styles.kpiValue} mono ${alert ? styles.kpiValueAlert : ''}`}>
        {formatRate(r)}
      </div>
      {/* 线性 meter —— 让「60%」有参照物。分母为 0 时不画轨道：
          画一条空轨道等于宣称「0%」，而真相是「算不出来」。 */}
      {r === null ? null : (
        <div className={styles.kpiTrack}>
          <div
            className={`${styles.kpiFill} ${r === 0 ? styles.kpiFillZero : ''}`}
            style={{ width: `${Math.min(100, r * 100)}%` }}
          />
        </div>
      )}
      <div className={`${styles.kpiDenom} mono`}>{denomLabel ?? formatFraction(m, n)}</div>
    </div>
  )
}

/** 计数型 KPI。值不是比率，所以不带百分比。 */
export function KpiCount({
  label,
  info,
  value,
  note,
  alert,
}: {
  label: string
  info?: string
  value: number | string
  note: string
  alert?: boolean
}) {
  return (
    <div className={`${styles.kpi} ${alert ? styles.kpiAlert : ''}`}>
      <div className={styles.kpiLabel}>
        {label}
        {info ? <InfoDot title={info} /> : null}
      </div>
      <div className={`${styles.kpiValue} mono ${alert ? styles.kpiValueAlert : ''}`}>{value}</div>
      <div className={styles.kpiDenom}>{note}</div>
    </div>
  )
}

/**
 * 降级态 KPI —— 采到了，但这个维度后端还没算。
 *
 * 和「空」必须分开：空是没采到，降级是采到了算不出来。
 * 文案说清楚缺什么，否则用户会以为是采集出了问题。
 */
export function KpiDegraded({
  label,
  info,
  reason,
  note,
}: {
  label: string
  info?: string
  reason: string
  note: string
}) {
  return (
    <div className={styles.kpi}>
      <div className={styles.kpiLabel}>
        {label}
        {info ? <InfoDot title={info} /> : null}
      </div>
      <div className={`${styles.kpiValue} ${styles.kpiValueMuted}`}>{reason}</div>
      <div className={styles.kpiDenom}>{note}</div>
    </div>
  )
}

/* ══════ Badge / InfoDot ══════ */

export type BadgeTone = 'neutral' | 'ok' | 'danger' | 'warning' | 'accent'

const BADGE_TONE: Record<BadgeTone, string> = {
  neutral: '',
  ok: styles.badgeOk,
  danger: styles.badgeDanger,
  warning: styles.badgeWarning,
  accent: styles.badgeAccent,
}

export function Badge({
  children,
  tone = 'neutral',
  dot,
}: {
  children: ReactNode
  tone?: BadgeTone
  dot?: boolean
}) {
  return (
    <span className={`${styles.badge} ${BADGE_TONE[tone]}`}>
      {dot ? <span className={styles.dot} /> : null}
      {children}
    </span>
  )
}

export function InfoDot({ title }: { title: string }) {
  return (
    <span className={styles.infoDot} title={title} role="img" aria-label={`口径：${title}`}>
      i
    </span>
  )
}

/* ══════ Tabs ══════ */

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

/* ══════ 表 ══════ */

export function Table({ children }: { children: ReactNode }) {
  return <table className={styles.table}>{children}</table>
}

/* ══════ 三态：每个数据组件必备 —— 加载 / 空 / 降级 ══════ */

export function Skeleton({ height = 16, width = '100%' }: { height?: number; width?: string }) {
  return <div className={styles.skeleton} style={{ height, width }} />
}

export function ErrorState({
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
    <div className={styles.errorBox}>
      <div style={{ flex: 1 }}>
        <div className={styles.errorTitle}>加载失败</div>
        <div className={styles.errorDetail}>
          接口 {status}
          {code ? ` · ${code}` : ''} · {message}
        </div>
      </div>
      {onRetry ? <Button onClick={onRetry}>重试</Button> : null}
    </div>
  )
}

export function EmptyState({ children }: { children: ReactNode }) {
  return <div className={styles.stateBox}>{children}</div>
}

/** 行内降级标记，用在矩阵格、表格单元里 */
export function Degraded({ children }: { children: ReactNode }) {
  return <span className={styles.degraded}>{children}</span>
}
