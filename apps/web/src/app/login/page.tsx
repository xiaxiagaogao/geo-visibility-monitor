import { AnswerCanvas, type CanvasMark } from '@/components/canvas/AnswerCanvas'

import { LoginForm } from './LoginForm'
import styles from './login.module.css'

/**
 * 登录页。
 *
 * 身份只有一条通道：**会话 Cookie**。`X-API-Key` 是机器凭证、权限等同超管，
 * 绝不打进前端包（API.md §1）—— 这一页曾经是个「粘贴 API Key」的表单，
 * 那套已经拆掉了。
 *
 * ── 结构 ──
 *
 * 风格情报 §5.2 首选的**左右劈开**：左侧是活的产品（Answer Canvas），
 * 右侧是表单、无卡片。§5.1 把「灰底 + 居中白卡片 + Logo + 欢迎回来」
 * 列为反模式 —— 上一版正是那个形状。
 *
 * 这是全站**唯一一个不登录也能看到的页面**，所以左侧必须让人看懂产品在做什么。
 *
 * ⚠️ **左侧那段回答是合成的，不是真实数据**，并且在画布上标着「示例内容」。
 * 用真实测量结果当门面就滑向「为了展示改产品」了。
 */

/**
 * 合成的演示回答。品牌与竞品是公开品牌名，内容是照真实回答的语气写的。
 *
 * ⚠️ 偏移量是**按码点**算的，且必须满足和真实数据同一条不变量：
 *   text.slice(offset, offset + term.length) === term
 * 第一版这里的偏移是我手数的，全错 —— 高亮落在了「价位」「跑者」上。
 * AnswerCanvas 现在会自己校验并跳过对不上的那一处（和证据页同一条规矩），
 * 所以即使写错也只会少画一个高亮，不会画到错的字上。
 */
const DEMO_TEXT =
  '如果预算在 500 元上下又想要稳定支撑，安踏的 C202 系列这两年进步很明显，' +
  '中底回弹和包裹都比同价位扎实。李宁的赤兔系列偏轻量，适合配速较快的跑者；' +
  '耐克则在缓震调校上更成熟，但同规格价格通常高一档。'

const DEMO_MARKS: CanvasMark[] = [
  { offset: 21, term: '安踏', kind: 'own', title: '本品 · 命中别名：安踏' },
  { offset: 56, term: '李宁', kind: 'rival', title: '竞品 · 李宁' },
  { offset: 77, term: '耐克', kind: 'rival', title: '竞品 · 耐克' },
]

const DEMO_CITES = [
  { index: 1, domain: 'www.163.com' },
  { index: 2, domain: 'best.pconline.com.cn' },
  { index: 3, domain: 'runrepeat.com' },
]

export default function LoginPage() {
  return (
    <div className={styles.wrap}>
      <section className={styles.pitch}>
        <div className={styles.brand}>
          <TraceMark />
          <span className={styles.brandName}>GEO 监测台</span>
        </div>

        <h1 className={styles.headline}>看 AI 怎么提到你</h1>

        <p className={styles.sub}>
          反复向千问、豆包、DeepSeek 问同一批问题，记录你的品牌有没有被提到、
          在第几位出现、AI 是照着谁的网页说的。
        </p>

        <div className={styles.canvasFrame}>
          <AnswerCanvas
            text={DEMO_TEXT}
            marks={DEMO_MARKS}
            citations={DEMO_CITES}
            model="tongyi"
            at="每条提问采样 3 次"
            animate
            synthetic
          />
        </div>

        <p className={styles.claim}>
          每一个百分比都能顺着标注回溯到某一条回答的第 N 个字符。
          算不出来的地方显示 <span className="mono">—</span>，不显示 0。
        </p>
      </section>

      <LoginForm />
    </div>
  )
}

/**
 * 字标 —— 一段被采样的信号：走平、一个尖峰、再走平。
 * 与侧栏那枚同源（`components/shell/Sidebar.tsx`）。
 */
function TraceMark() {
  return (
    <svg
      className={styles.mark}
      viewBox="0 0 30 30"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <rect x="1.4" y="1.4" width="27.2" height="27.2" rx="4" strokeWidth="1.1" opacity="0.35" />
      <path d="M7 5.8v1.8M12 5.8v1.8M17 5.8v1.8M22 5.8v1.8" strokeWidth="1" opacity="0.4" />
      <path d="M4 17h4.4l1.9-3.2 2 8.6 2.3-11.9 2.2 6.8 1.7-2.8H26" />
    </svg>
  )
}
