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
 */
export default function LoginPage() {
  return (
    <div className={styles.wrap}>
      <LoginForm />
    </div>
  )
}
