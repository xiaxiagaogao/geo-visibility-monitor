'use client'

import { useEffect, useRef, useState } from 'react'

import { formatFraction, formatRate } from '@/lib/l3/rates'
import { comparableSegments, timeAxis, type TrendPoint } from '@/lib/l3/trend'

import styles from './trendArea.module.css'

/**
 * 历次运行 —— 12 次运行沿真实时间轴摊开，画成**单色面积图**。
 *
 * 为什么是面积不是折线（`STYLE-BRIEF.md` §8.2）：这条序列的量纲是
 * **0–100% 的比率，零点有意义**。面积把「离零点多远」变成可以一眼估量的
 * 体量，而折线只给出一条高度。同时它让这张图在缩到 128px 高时仍然有主体 ——
 * 一条 2px 的线在这个高度上几乎只是装饰。
 *
 * **单色**：数据只用一个色相（强调色）。竞品是中性灰，不是第二个色相 ——
 * 这是 emphasis（突出一个、其余灰化），不是类目色板。
 *
 * 三件它必须说清楚、而一条普通折线说不清楚的事：
 *
 * 1. **断口。** 平台集变过的地方**面积和线都是断开的**，两段之间不连。
 *    连起来就是把口径变化伪装成表现变化 —— run 快照这套机制存在的
 *    全部理由就是防这件事（README §2.1）。
 * 2. **分母不完整的那几次**用空心方标，不是实心。partial 的 run 比率会偏高，
 *    画成和完整运行一样的点，等于说它们一样可信。
 * 3. **竞品是一条区间带，不是 7 条线。** 运营要问的是「我在场上处于什么位置」，
 *    那是区间问题；7 条线在 130px 高的带子里是一团面条。
 *    ⚠️ 换成面积图之后，竞品带**必须画在本品面积之上**并且带两道实线边 ——
 *    画在下面的话，本品面积一路填到零点，会把带子的下沿整个盖掉，
 *    而「我在不在竞品区间内」这个问题正好要看下沿。
 *
 * 横轴按**真实时间**排 —— 12 次里有 5 次挤在同一天，等距排会把
 * 「密集重测」和「隔天一测」画成同一件事。
 */

const H = 128 // 绘图区高
const PAD_T = 22 // 顶端要给段标（平台集）留位
const PAD_B = 18
const PAD_X = 12
const GRID = [0, 0.25, 0.5, 0.75, 1]

export function TrendArea({
  points,
  activeRunId,
  onPick,
}: {
  points: TrendPoint[]
  activeRunId: number | null
  onPick: (runId: number) => void
}) {
  const box = useRef<HTMLDivElement>(null)
  const [w, setW] = useState(0)
  const [hover, setHover] = useState<number | null>(null)

  // 真实像素坐标 —— 不用 preserveAspectRatio="none"，那会把方标压成长方形
  useEffect(() => {
    const el = box.current
    if (!el) return
    const ro = new ResizeObserver(([e]) => setW(e.contentRect.width))
    ro.observe(el)
    setW(el.getBoundingClientRect().width)
    return () => ro.disconnect()
  }, [])

  const axis = timeAxis(points)
  const inner = Math.max(0, w - PAD_X * 2)
  const x = (i: number) => PAD_X + axis[i] * inner
  const y = (r: number) => PAD_T + (1 - r) * (H - PAD_T - PAD_B)

  const segments = comparableSegments(points)
  const indexOf = new Map(points.map((p, i) => [p.runId, i]))
  const hovered = hover === null ? null : points[hover]

  return (
    <div className={styles.wrap}>
      <div className={styles.box} ref={box}>
        {w > 0 ? (
          <svg
            className={styles.svg}
            width={w}
            height={H}
            role="img"
            aria-label={`${points.length} 次运行的提及率记录`}
          >
            <defs>
              <linearGradient id="areaFade" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" className={styles.areaTop} />
                <stop offset="100%" className={styles.areaBottom} />
              </linearGradient>
            </defs>

            {/* 横向刻度 */}
            {GRID.map((g) => (
              <line
                key={g}
                x1={0}
                x2={w}
                y1={y(g)}
                y2={y(g)}
                className={g === 0 ? styles.baseline : styles.gridline}
              />
            ))}

            {/* 竞品区间 —— **每次运行一根须**，不是一条连续的带。
                这条改动不只是为了让开面积：一条带会把 min/max 在两次运行**之间插值**，
                而竞品数值只在运行发生的那一刻存在，中间那段是画出来的、不是测出来的。
                须只陈述测到的东西 —— 和这个产品其余部分同一条规矩。
                顺带它也不再和本品面积抢地盘：须是线，面积是面，两者不会糊在一起。 */}
            {points.map((p, i) => {
              if (p.competitorBand === null) return null
              const { min, max } = p.competitorBand
              const cx = x(i)
              return (
                <g key={`whisker-${p.runId}`} className={styles.whisker}>
                  <line x1={cx} x2={cx} y1={y(max)} y2={y(min)} />
                  <line x1={cx - 3} x2={cx + 3} y1={y(max)} y2={y(max)} />
                  <line x1={cx - 3} x2={cx + 3} y1={y(min)} y2={y(min)} />
                </g>
              )
            })}

            {/* 本品的面积。一段一段画 —— 断口处不跨过去。
                渐变从曲线顶端的强调色淡入到零点近乎透明：它是**同一个色相的
                单序列淡出**，不是把高度二次编码成深浅（那是 value-ramp 反模式）。 */}
            {segments.map((seg, si) => {
              const drawable = seg.filter((p) => p.r !== null)
              if (drawable.length < 2) return null
              const pts = drawable.map((p) => {
                const i = indexOf.get(p.runId)!
                return [x(i), y(p.r!)] as const
              })
              const x0 = pts[0][0]
              const x1 = pts[pts.length - 1][0]
              const d = [
                `M${x0},${y(0)}`,
                ...pts.map(([px, py]) => `L${px},${py}`),
                `L${x1},${y(0)}`,
                'Z',
              ].join(' ')
              return <path key={`area-${si}`} d={d} className={styles.area} />
            })}

            {/* 本品的线 —— 压在最上面。面积会被竞品带罩一层灰，
                这条 2px 的强调色线保证主角在任何重叠处都不糊。 */}
            {segments.map((seg, si) => {
              const drawable = seg.filter((p) => p.r !== null)
              if (drawable.length < 2) return null
              return (
                <polyline
                  key={`trace-${si}`}
                  className={styles.trace}
                  points={drawable
                    .map((p) => {
                      const i = indexOf.get(p.runId)!
                      return `${x(i)},${y(p.r!)}`
                    })
                    .join(' ')}
                />
              )
            })}

            {/* 断口：纸在这里是断的。两道竖虚线中间留白，不是一条彩色分隔线 */}
            {points.map((p, i) => {
              if (!p.breaks.includes('platforms') || i === 0) return null
              const mid = (x(i - 1) + x(i)) / 2
              return (
                <g key={`break-${p.runId}`}>
                  <line x1={mid - 4} x2={mid - 4} y1={2} y2={H - PAD_B} className={styles.tear} />
                  <line x1={mid + 4} x2={mid + 4} y1={2} y2={H - PAD_B} className={styles.tear} />
                  <rect x={mid - 4} y={2} width={8} height={H - PAD_B - 2} className={styles.gap} />
                </g>
              )
            })}

            {/* 每一段的平台集，标在这一段顶端。
                没有这个标注，一条碎成 5 段的线看起来只是「图坏了」；
                有了它，读者立刻知道每一段是在什么条件下采的、以及为什么不能接着比。 */}
            {segments.map((seg, si) => {
              const first = indexOf.get(seg[0].runId)!
              const last = indexOf.get(seg[seg.length - 1].runId)!
              const mid = (x(first) + x(last)) / 2
              const width = x(last) - x(first)
              const text = seg[0].platforms.join('+') || '未选平台'
              // 段太窄就不标 —— 一个被截断的平台名比不标更糟
              if (width < 34 && seg.length > 1) return null
              return (
                <text
                  key={`seg-${si}`}
                  x={mid}
                  y={10}
                  className={styles.segLabel}
                  textAnchor="middle"
                >
                  {text}
                </text>
              )
            })}

            {/* 每次运行一个标记 */}
            {points.map((p, i) => {
              if (p.r === null) return null
              const active = p.runId === activeRunId
              const s = active ? 5 : 4
              return (
                <g key={p.runId}>
                  {active ? (
                    <line
                      x1={x(i)}
                      x2={x(i)}
                      y1={y(p.r)}
                      y2={y(0)}
                      className={styles.drop}
                    />
                  ) : null}
                  <rect
                    x={x(i) - s}
                    y={y(p.r) - s}
                    width={s * 2}
                    height={s * 2}
                    className={`${styles.mark} ${p.incomplete ? styles.markPartial : ''} ${
                      active ? styles.markActive : ''
                    }`}
                  />
                  {/* 这次运行带了说明 —— 只标一下，不替读者下结论 */}
                  {p.breaks.includes('note') ? (
                    <path
                      d={`M${x(i)},${H - PAD_B + 3} l3.5,5 h-7 Z`}
                      className={styles.noteFlag}
                    />
                  ) : null}
                </g>
              )
            })}

            {/* 命中区：比标记大得多，好点 */}
            {points.map((p, i) => (
              <rect
                key={`hit-${p.runId}`}
                x={x(i) - 14}
                y={0}
                width={28}
                height={H}
                className={styles.hit}
                onMouseEnter={() => setHover(i)}
                onMouseLeave={() => setHover(null)}
                onClick={() => onPick(p.runId)}
              />
            ))}
          </svg>
        ) : null}

        {hovered ? (
          <div
            className={styles.tip}
            style={{
              left: `${(axis[hover!] * inner + PAD_X) / Math.max(w, 1) * 100}%`,
            }}
          >
            <div className={styles.tipHead}>
              <span className="mono">{fmtDate(hovered.at)}</span>
              <span className={styles.tipRun}>run #{hovered.runId}</span>
            </div>
            <div className={styles.tipRate}>
              <strong className="mono">{formatRate(hovered.r)}</strong>
              <span className="mono">{formatFraction(hovered.m, hovered.n)}</span>
            </div>
            {hovered.competitorBand ? (
              <div className={styles.tipRow}>
                竞品区间 {formatRate(hovered.competitorBand.min)} ~{' '}
                {formatRate(hovered.competitorBand.max)}
              </div>
            ) : null}
            <div className={styles.tipRow}>平台 {hovered.platforms.join(' · ') || '—'}</div>
            {hovered.incomplete ? (
              <div className={styles.tipWarn}>分母不完整 —— 这个比率会偏高</div>
            ) : null}
            {hovered.note ? <div className={styles.tipNote}>{hovered.note}</div> : null}
          </div>
        ) : null}
      </div>

      {/* 纵轴刻度写在纸的左边缘外，不压在数据上 */}
      <div className={styles.yLabels} aria-hidden="true">
        {GRID.slice()
          .reverse()
          .map((g) => (
            <span key={g}>{Math.round(g * 100)}</span>
          ))}
      </div>

      <div className={styles.xLabels} aria-hidden="true">
        <span>{points.length ? fmtDate(points[0].at) : ''}</span>
        <span>{points.length ? fmtDate(points[points.length - 1].at) : ''}</span>
      </div>
    </div>
  )
}

function fmtDate(iso: string): string {
  const d = new Date(iso)
  const p = (x: number) => String(x).padStart(2, '0')
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}
