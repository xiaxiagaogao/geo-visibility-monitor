import { test as base, expect, type Page } from '@playwright/test'

/**
 * 公用夹具：只读护栏 + 登录 + 控制台守卫。
 */

/* ══════════════════════════════════════════════════════════════════
   只读护栏
   ══════════════════════════════════════════════════════════════════ */

/**
 * 挡住一切会改动生产数据的请求。
 *
 * 这套测试跑在生产数据上（见 playwright.config.ts 顶部）。「记得别点立即运行」
 * 是守不住的 —— 一次误点就是真建 job、真花额度、撤不回来。所以在网络层拦死：
 * **除登录外，任何非 GET 的 `/v1` 请求都 abort**，并把它记下来让测试失败。
 *
 * 用 abort 而不是只记录：如果只记录，请求已经发出去了，护栏就是事后诸葛。
 */
const WRITE_ALLOWLIST = ['/v1/auth/login', '/v1/auth/logout']

export async function guardReadOnly(page: Page, violations: string[]) {
  await page.route('**/v1/**', async (route) => {
    const req = route.request()
    const method = req.method()
    const url = new URL(req.url()).pathname

    if (method === 'GET' || method === 'HEAD' || method === 'OPTIONS') {
      return route.continue()
    }
    if (WRITE_ALLOWLIST.some((p) => url.startsWith(p))) {
      return route.continue()
    }

    violations.push(`${method} ${url}`)
    await route.abort('blockedbyclient')
  })
}

/* ══════════════════════════════════════════════════════════════════
   登录
   ══════════════════════════════════════════════════════════════════ */

/**
 * 凭据只从环境变量来，**永远不写进仓库**。
 *
 *   E2E_EMAIL=... E2E_PASSWORD=... pnpm e2e
 *
 * 没给凭据时，需要登录的测试**跳过**而不是失败 —— 一个因为没配凭据而红的
 * 测试套件，跑几次就没人看了。登录页那档不需要凭据，任何时候都跑。
 */
export const CREDS = {
  email: process.env.E2E_EMAIL ?? '',
  password: process.env.E2E_PASSWORD ?? '',
}
export const hasCreds = Boolean(CREDS.email && CREDS.password)

/**
 * 直接打登录接口拿 Cookie，不走 UI 表单。
 *
 * 为什么不走表单：那样每个用例都要重跑一遍登录动画与跳转，慢且脆。
 * 登录**表单本身**由 `login.spec.ts` 单独测，职责分开。
 */
async function loginViaApi(page: Page) {
  const res = await page.request.post('/v1/auth/login', {
    data: { email: CREDS.email, password: CREDS.password },
  })
  if (!res.ok()) {
    throw new Error(
      `登录失败 ${res.status()} —— 检查 E2E_EMAIL / E2E_PASSWORD。` +
        `响应：${(await res.text()).slice(0, 200)}`,
    )
  }
}

/* ══════════════════════════════════════════════════════════════════
   夹具
   ══════════════════════════════════════════════════════════════════ */

/**
 * 未登录时 `GET /v1/auth/me` 返回 401 是**正确行为**，但 Chrome 会把它记成一条
 * console error（`Failed to load resource: … 401`）。把这类噪音放过 ——
 * 但**只放过 401**，其余 4xx/5xx 与任何 React / JS 报错照旧算失败。
 */
function isExpectedNoise(text: string): boolean {
  return /Failed to load resource.*\b401\b/.test(text)
}

/**
 * 测试**故意**制造的网络错误。
 *
 * 测错误路径的用例会自己 `route.abort()`，浏览器随即记一条
 * `net::ERR_FAILED` —— 那是这条用例要的结果，不是缺陷。
 * 但真实的网络故障走的是另一条路：dev 代理连不上线上时返回的是 **500**
 * （见 `e2e/README.md`「红了先看这三件」第 3 条），不是 ERR_FAILED。
 * 所以放过 ERR_FAILED 不会掩盖真问题。
 *
 * 仍然只在用例显式声明之后才放过 —— 默认一律算失败。
 */
const DELIBERATE_ABORT = /Failed to load resource.*net::ERR_FAILED/

export const test = base.extend<{
  /** 未登录的页面，带只读护栏与控制台守卫 */
  guardedPage: Page
  /** 已登录的页面 */
  authedPage: Page
  /** 声明这条用例会自己 abort 请求，别把由此产生的控制台报错算成失败 */
  expectAbortedRequests: (on: boolean) => void
}>({
  expectAbortedRequests: async ({}, use) => {
    await use(() => {
      /* 实际生效在 authedPage 里，这里只是让用例能声明 */
    })
  },
  guardedPage: async ({ page }, use) => {
    const violations: string[] = []
    const consoleErrors: string[] = []
    await guardReadOnly(page, violations)

    // 控制台报错**当成失败**。改版期间「页面看着好好的、控制台在刷 React 报错」
    // 出现过不止一次，靠人眼截图是发现不了的。
    page.on('console', (m) => {
      if (m.type() === 'error' && !isExpectedNoise(m.text())) consoleErrors.push(m.text())
    })
    page.on('pageerror', (e) => consoleErrors.push(String(e)))

    await use(page)

    expect(violations, '有测试试图改动生产数据').toEqual([])
    expect(consoleErrors, '浏览器控制台有报错').toEqual([])
  },

  authedPage: async ({ page }, use) => {
    test.skip(!hasCreds, '没有 E2E_EMAIL / E2E_PASSWORD，跳过需要登录的用例')
    const violations: string[] = []
    const consoleErrors: string[] = []
    await guardReadOnly(page, violations)
    page.on('console', (m) => {
      if (m.type() !== 'error') return
      if (isExpectedNoise(m.text())) return
      // 用例自己 abort 出来的那些，见 DELIBERATE_ABORT 的注释
      if (DELIBERATE_ABORT.test(m.text())) return
      consoleErrors.push(m.text())
    })
    page.on('pageerror', (e) => consoleErrors.push(String(e)))

    await loginViaApi(page)
    await use(page)

    expect(violations, '有测试试图改动生产数据').toEqual([])
    expect(consoleErrors, '浏览器控制台有报错').toEqual([])
  },
})

export { expect }

/* ══════════════════════════════════════════════════════════════════
   小工具
   ══════════════════════════════════════════════════════════════════ */

/** 整页重载后再读主题相关的值 —— 运行时翻 data-theme 会拿到过渡中间值。 */
export async function setTheme(page: Page, theme: 'dark' | 'light') {
  await page.evaluate((t) => {
    if (t === 'dark') localStorage.removeItem('geo-theme')
    else localStorage.setItem('geo-theme', 'light')
  }, theme)
  await page.reload({ waitUntil: 'networkidle' })
}

/** 找出这一页所有失败的网络请求（4xx/5xx 与直接失败的）。 */
export function trackFailedRequests(page: Page) {
  const failed: string[] = []
  page.on('response', (r) => {
    // 401 是未登录态的**正确**行为，不算失败
    if (r.status() >= 400 && r.status() !== 401) failed.push(`${r.status()} ${r.url()}`)
  })
  page.on('requestfailed', (r) => {
    // 只读护栏自己 abort 的那些不算网络故障，护栏另有断言
    if (r.failure()?.errorText !== 'net::ERR_BLOCKED_BY_CLIENT') {
      failed.push(`FAILED ${r.url()}`)
    }
  })
  return failed
}
