import styles from './login.module.css'

/**
 * 登录页 —— 这一轮只出样式，接口对接排在 API 那一步。
 *
 * 届时的流程（docs/28 §5，已定）：
 *   1. POST /qa/login（form-urlencoded，字段 key）→ 后端下发 HttpOnly Cookie
 *   2. 探针 GET /v1/config/metrics：200 = 成功，401 = key 错
 *      —— 不去解析 302 的 Location，探针才是「到底认没认证」的真答案
 *   3. 成功后把同一个 key 写进 sessionStorage 供写操作用，然后跳 /
 *
 * 读接口靠 Cookie，写接口靠 X-API-Key 头。Cookie 永远不对写方法生效 ——
 * 这条 CSRF 红线有测试守着，不许为了方便放开。
 */
export default function LoginPage() {
  return (
    <div className={styles.wrap}>
      <form className={styles.card} action="/qa/login" method="post">
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

        <p className={styles.lede}>
          输入 API Key 以查看监测数据。读接口凭 Cookie，写接口另需请求头。
        </p>

        <label className={styles.label} htmlFor="key">
          API Key
        </label>
        <input
          className={styles.input}
          id="key"
          name="key"
          type="password"
          autoComplete="off"
          placeholder="粘贴 API Key"
        />

        <button className={styles.submit} type="submit">
          登录
        </button>

        <p className={styles.note}>
          当前表单直接提交给后端现成的 <code>POST /qa/login</code>，成功后落到 <code>/qa</code>。
          换成「登录后跳看板 + 存 key 供写操作用」的版本排在 API 对接那一步。
        </p>
      </form>
    </div>
  )
}
