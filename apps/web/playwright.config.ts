import { defineConfig, devices } from '@playwright/test'

/**
 * 端到端冒烟测试。
 *
 * ## ⚠️ 这套测试跑在**生产数据**上
 *
 * `next.config.ts` 的 dev rewrites 把 `/v1` 代理到 `https://geo.example.com` ——
 * 本机没有独立后端，也没有测试库。所以：
 *
 *   **每一个测试都必须是只读的。** 绝不能点「立即运行」（真建 job、真花额度、
 *   撤不回来），也不能新建/改/删品牌、任务、用户。
 *
 * 这条不靠自觉守：`e2e/fixtures.ts` 装了一道路由拦截，**除登录外的任何
 * 非 GET `/v1` 请求一律 abort 并让测试失败**。将来谁不小心写了个写操作，
 * 会当场炸掉，而不是默默改了线上数据。
 *
 * ## 断言写「不变量」，不写具体数字
 *
 * 生产数据每天在变。断言「12 次运行」明天就红了，而那不是回归。
 * 所以断言的是结构与口径不变量 —— 例如「每个比率读数旁边必须有分母」——
 * 这也正是这个产品最该被钉住的东西。
 */

const PORT = Number(process.env.E2E_PORT ?? 3100)

export default defineConfig({
  testDir: './e2e',
  // 生产数据是共享的，并发跑会互相干扰登录态；而且这套本来就只有几十个断言
  workers: 1,

  /**
   * **重试一次 —— 因为 `/v1` 打的是公网上的线上服务。**
   *
   * 实测这台机器到 geo.example.com 的 TLS 握手会间歇性被 ECONNRESET
   * （dev 代理日志里是 `Failed to proxy … Client network socket disconnected`），
   * 于是代理返回 500、页面渲染成 Fault、用例找不到任何元素。
   * 同一时刻直连生产 5/5 正常 —— 是瞬时抖动，不是故障。
   * 用例数从 31 涨到 36 之后撞上的概率明显变高。
   *
   * **这不是在掩盖缺陷**：真的断言失败两次都会红；瞬时重置第二次就过。
   * 而且 Playwright 把重试后才过的记成 **flaky** 单独报，不会伪装成绿。
   * 看到 flaky 就去看 `preview_logs` 里有没有 `Failed to proxy`。
   */
  retries: 1,
  fullyParallel: false,
  // 网络要走一趟公网到 VPS，默认 5s 不够
  timeout: 45_000,
  expect: { timeout: 10_000 },
  reporter: process.env.CI ? 'github' : [['list']],
  use: {
    baseURL: `http://localhost:${PORT}`,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: `pnpm dev --port ${PORT}`,
    url: `http://localhost:${PORT}/login`,
    reuseExistingServer: true,
    timeout: 120_000,
  },
})
