import { LoginForm } from './LoginForm'
import styles from './login.module.css'

/**
 * 登录页。
 *
 * 身份只有一条通道：**会话 Cookie**。`X-API-Key` 是机器凭证、权限等同超管，
 * 绝不打进前端包（API.md §1）—— 这一页曾经是个「粘贴 API Key」的表单，
 * 那套已经拆掉了。
 *
 * AuthProvider 在根布局，这里直接用 useAuth 即可。
 *
 * ── 这一页为什么要自己说清楚产品是什么 ────────────────────────
 *
 * 它是全站**唯一一个不登录也能看到的页面**。上一版它只有一句
 * 「使用账号登录以查看监测数据」—— 一个进不去的人从这里带不走任何信息。
 *
 * 版式沿用记录纸的语言：整页铺分钟刻线，中间一条**走平的触针线**。
 * 「没有记录」在这个产品里就是一条走平的线 —— 未登录状态和这个隐喻
 * 是同一件事，不用另编一个。
 *
 * ⚠️ **这一页不放任何真实数字。** 说的全是能力（做什么、口径是什么），
 * 不是成果（测到了多少）。放真实数据就滑向「为了展示改产品」了。
 */
export default function LoginPage() {
  return (
    <div className={styles.wrap}>
      <div className={styles.flatline} aria-hidden="true" />

      <section className={styles.pitch}>
        <div className={styles.brand}>
          <TraceMark />
          <div>
            <div className={styles.brandName}>GEO 监测台</div>
            <div className={styles.brandSub}>AI 回答可见度记录</div>
          </div>
        </div>

        <h1 className={styles.headline}>
          消费者去问 AI 买什么，你的品牌出现了吗？
        </h1>

        <p className={styles.sub}>
          反复向中文 AI 助手问同一批问题，记录你的品牌有没有被提到、
          在第几位出现、AI 是照着谁的网页说的。
        </p>

        <p className={styles.claim}>
          每一个百分比都能顺着标注回溯到某一条回答的第 N 个字符。
          算不出来的地方显示「—」，不显示 0。
        </p>
      </section>

      <LoginForm />
    </div>
  )
}

/**
 * 字标 —— 一段触针走出来的记录：走平、一个尖峰、再走平。
 * 与侧栏那枚同源（`components/shell/Sidebar.tsx`）。
 *
 * 上一版这里是个装在渐变方块里的放大镜。放大镜是「搜索」的通用符号，
 * 和这个产品在做的事没有关系；渐变则是纯装饰。
 */
function TraceMark() {
  return (
    <svg
      className={styles.mark}
      viewBox="0 0 30 30"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <rect x="1.4" y="1.4" width="27.2" height="27.2" rx="2.5" strokeWidth="1.3" opacity="0.4" />
      <path d="M7 5.6v2M12 5.6v2M17 5.6v2M22 5.6v2" strokeWidth="1.1" opacity="0.45" />
      <path d="M4 17h4.4l1.9-3.2 2 8.6 2.3-11.9 2.2 6.8 1.7-2.8H26" />
    </svg>
  )
}
