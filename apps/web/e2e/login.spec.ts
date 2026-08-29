import { test, expect, setTheme, trackFailedRequests } from './fixtures'

/**
 * 登录页 —— **全站唯一免登录可见的页面**，也是门面。
 * 这一档不需要凭据，任何环境都跑。
 */

test.describe('登录页', () => {
  test('签名物件在，且高亮落在正确的字上', async ({ guardedPage: page }) => {
    await page.goto('/login', { waitUntil: 'networkidle' })

    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    await expect(page.getByLabel('工作邮箱')).toBeVisible()
    await expect(page.getByLabel('密码')).toBeVisible()

    // Answer Canvas：必须有标记，且**每一处标记的字面都是回答正文里的一段**。
    // 组件内部有同一条不变量自检（切出来的字必须等于标注说的字），这里从外面
    // 再钉一次 —— 做登录页时手数的偏移全错过，高亮当时落在了「价位」「跑者」上，
    // 页面看着完全正常。这是靠截图发现不了、只能靠断言的那类错。
    const marks = page.locator('mark')
    const n = await marks.count()
    expect(n, '一处高亮都没有').toBeGreaterThan(0)

    const answer = (await page.locator('mark').first().locator('xpath=..').innerText())
      .replace(/\s+/g, '')
    for (let i = 0; i < n; i++) {
      const term = (await marks.nth(i).innerText()).replace(/\s+/g, '')
      expect(term, `第 ${i} 处高亮是空的`).not.toBe('')
      expect(answer.includes(term), `第 ${i} 处高亮「${term}」不在回答正文里`).toBe(true)
    }

    // 演示数据必须**标着是演示**，不能让人以为是真实测量结果
    await expect(page.getByText('示例内容')).toBeVisible()
  })

  test('三种自托管字体都真的加载了，没有掉回系统字', async ({ guardedPage: page }) => {
    await page.goto('/login', { waitUntil: 'networkidle' })

    const loaded = await page.evaluate(async () => {
      await document.fonts.ready
      return [...document.fonts].map((f) => `${f.family}|${f.status}`)
    })
    for (const family of ['Geist', 'Geist Mono', 'Noto Sans SC Display']) {
      expect(loaded.some((f) => f.startsWith(`${family}|loaded`)), `${family} 没加载`).toBe(
        true,
      )
    }
  })

  test('默认是暗色 —— 新访客不带 localStorage', async ({ guardedPage: page }) => {
    await page.goto('/login', { waitUntil: 'networkidle' })
    // 服务端渲染的 <html> 不带 data-theme；脚本只在明确存了 light 时才切
    expect(await page.locator('html').getAttribute('data-theme')).toBeNull()
    const canvas = await page.evaluate(() =>
      getComputedStyle(document.documentElement).getPropertyValue('--canvas').trim(),
    )
    expect(canvas.toLowerCase()).toBe('#08090b')
  })

  test('375px 窄屏不横向溢出', async ({ guardedPage: page }) => {
    await page.setViewportSize({ width: 375, height: 812 })
    await page.goto('/login', { waitUntil: 'networkidle' })
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    )
    expect(overflow, '出现了横向滚动').toBeLessThanOrEqual(0)
  })

  test('浅色档也没有静态资源失败', async ({ guardedPage: page }) => {
    const failed = trackFailedRequests(page)
    await page.goto('/login', { waitUntil: 'networkidle' })
    await setTheme(page, 'light')
    expect(await page.locator('html').getAttribute('data-theme')).toBe('light')
    expect(failed).toEqual([])
  })
})
