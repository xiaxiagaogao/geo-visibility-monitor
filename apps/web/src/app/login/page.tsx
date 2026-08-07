import styles from './login.module.css'

/**
 * 登录页 —— 只有版式，提交禁用，接口对接排在下一轮。
 *
 * 这一页原来是个 `<form action="/qa/login" method="post">` 的明文 API Key 输入框，
 * 配套的设计是「登录成功后把这个 key 存进 sessionStorage 供写操作用」。
 * **那套整个作废，而且不只是过期，是安全问题**：
 * X-API-Key 是机器凭证（运维脚本 / CI），权限等同超管，
 * 一旦进了前端包就等于把超管权限发给每个能打开浏览器的人（API.md §1）。
 *
 * 现在的身份通道只有一条：会话 Cookie。接口对接时按 API.md §2 走 ——
 *   1. POST /v1/auth/login，**JSON** 体 { email, password }（不是表单）
 *   2. 200 会下发两个 Cookie：geo_session（HttpOnly，JS 读不到）
 *      与 geo_csrf（刻意非 HttpOnly，前端要读它回填 X-CSRF-Token）
 *   3. fetch 一律 credentials: 'include' —— 跨站不带这个就没有身份
 *
 * 登录失败一律 401 且只有一句话，不区分「用户不存在 / 密码错 / 账号停用」。
 * 前端也不许据此提示「该邮箱未注册」—— 那等于把账号枚举接口做到 UI 上。
 */
export default function LoginPage() {
  return (
    <div className={styles.wrap}>
      {/* 没有 action：原来的 action="/qa/login" 已拆掉；字段与按钮全 disabled，提交不了 */}
      <form className={styles.card}>
        <div className={styles.brand}>
          <div className={styles.mark}>
            <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="11" cy="11" r="7" />
              <path d="M21 21l-4.3-4.3" />
            </svg>
          </div>
          <div>
            <div className={styles.brandName}>GEO 监测台</div>
            <div className={styles.brandSub}>AI 回答可见度监测</div>
          </div>
        </div>

        <p className={styles.lede}>使用账号登录以查看监测数据。</p>

        <label className={styles.label} htmlFor="email">
          邮箱
        </label>
        <input
          className={styles.input}
          id="email"
          name="email"
          type="email"
          autoComplete="username"
          placeholder="you@example.com"
          disabled
        />

        <label className={styles.label} htmlFor="password">
          密码
        </label>
        <input
          className={styles.input}
          id="password"
          name="password"
          type="password"
          autoComplete="current-password"
          disabled
        />

        <button className={styles.submit} type="submit" disabled>
          登录
        </button>

        <p className={styles.note}>
          接口尚未对接，表单暂不可用。下一轮接上 <code>POST /v1/auth/login</code>，
          成功后跳总览。
        </p>
      </form>
    </div>
  )
}
