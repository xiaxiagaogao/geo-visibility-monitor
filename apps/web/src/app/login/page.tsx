import styles from './login.module.css'

/**
 * 登录页 —— 这一轮只出样式，接口对接排在下一步（API 阶段）。
 *
 * 届时的流程（docs/28 §5，已定，不用再讨论）：
 *   1. POST /qa/login（form-urlencoded，字段 key）→ 后端下发 HttpOnly Cookie
 *   2. 探针 GET /v1/config/metrics：200 = 成功，401 = key 错
 *      —— 不去解析 302 的 Location，探针才是「到底认没认证」的真答案
 *   3. 成功后把同一个 key 写进 sessionStorage 供写操作用，然后跳 /
 *
 * 读接口靠 Cookie，写接口靠 X-API-Key 头。Cookie 永远不对写方法生效。
 */
export default function LoginPage() {
  return (
    <div className={styles.wrap}>
      <form className={styles.card} action="/qa/login" method="post">
        <h1 className={styles.logo}>GEO 监测台</h1>
        <p className={styles.sub}>
          输入 API Key 以查看监测数据。
          <br />
          读接口凭 Cookie，写接口另需请求头。
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
          当前表单直接提交给后端现成的 <code>POST /qa/login</code>，成功后会落到 <code>/qa</code>。
          换成「登录后跳看板 + 存 key 供写操作用」的版本，排在 API 对接那一步。
        </p>
      </form>
    </div>
  )
}
