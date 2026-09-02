import { test, expect } from './fixtures'

/**
 * 仪表盘的三个交互件：面积图、表格孪生、折叠提示条。
 *
 * 这三个都是这一轮新做/改做的，而且都**靠看截图发现不了回归** ——
 * 点了没反应、展开后内容没渲染、路由没跟上，截图上全都一模一样。
 */

/** 打开第一个任务的详情页。 */
async function openFirstTask(page: import('@playwright/test').Page) {
  await page.goto('/tasks', { waitUntil: 'networkidle' })
  // :not([href$="/new"]) 是必须的 —— 页头的「新建任务 +」也是 /tasks/ 开头，
  // 不排掉就会点进新建表单，而后面的断言会以很难懂的方式失败
  await page.locator('a[href^="/tasks/"]:not([href$="/new"])').first().click()
  await page.waitForLoadState('networkidle')
  await expect(page.getByRole('img', { name: /次运行的提及率记录/ })).toBeVisible()
}

test.describe('历次运行面积图', () => {
  test('画的是面积不是折线，且竞品是须不是带', async ({ authedPage: page }) => {
    await openFirstTask(page)
    const svg = page.getByRole('img', { name: /次运行的提及率记录/ })

    // 面积：闭合到零点的 path + 渐变 def。折线时代这两样都不存在。
    await expect(svg.locator('defs linearGradient')).toHaveCount(1)
    const areas = svg.locator('path[d^="M"]')
    expect(await areas.count(), '没有面积路径').toBeGreaterThan(0)

    // 竞品：须（每次运行三条线：竖线 + 两个端帽），**不是** polygon 区间带。
    // 带会把 min/max 在两次运行之间插值，那段没测过。
    const bands = svg.locator('polygon')
    expect(await bands.count(), '竞品又变回区间带了 —— 那会插值出没测过的值').toBe(0)
  })

  test('点图上一次运行会切到那一次（换路由，不是换查询参数）', async ({
    authedPage: page,
  }) => {
    await openFirstTask(page)
    const before = page.url()

    // 命中区带 data-run-id —— SVG 里还有方标和断口留白两种 rect，
    // 靠 nth 位置去点是猜的
    const hits = page.locator('svg [data-run-id]')
    const n = await hits.count()
    expect(n, '没有可点的运行').toBeGreaterThan(0)
    const targetRun = await hits.last().getAttribute('data-run-id')
    await hits.last().click({ force: true })
    await page.waitForLoadState('networkidle')

    // 运营要把某一次运行的链接发给客户 —— 所以必须是真实路由
    // 点了哪一次就必须落到哪一次 —— 不是「随便跳到某个 run」
    await expect(page).toHaveURL(new RegExp(`/tasks/\\d+/runs/${targetRun}$`))
    expect(page.url()).not.toBe(before)
  })

  test('图例画的形状和图上一致', async ({ authedPage: page }) => {
    await openFirstTask(page)
    // 图上是须，图例就必须是须。图例画个灰方块的话，读者会去图上找一条带。
    await expect(page.getByText(/竞品区间.*每次运行/)).toBeVisible()
  })
})

test.describe('表格孪生', () => {
  test('默认收起；展开后每一行的比率都带着分母', async ({ authedPage: page }) => {
    await openFirstTask(page)
    const details = page.locator('details').first()
    const summary = details.locator('summary')

    await expect(summary).toBeVisible()
    expect(await details.evaluate((d: HTMLDetailsElement) => d.open), '默认应该是收起的').toBe(
      false,
    )

    await summary.click()
    expect(await details.evaluate((d: HTMLDetailsElement) => d.open)).toBe(true)

    const rows = details.locator('tbody tr')
    const n = await rows.count()
    expect(n, '展开了但一行都没有').toBeGreaterThan(0)

    // 比率和分母同框 —— 表格里也不松
    for (let i = 0; i < n; i++) {
      const cells = rows.nth(i).locator('td')
      const rate = (await cells.nth(1).innerText()).trim()
      const denom = (await cells.nth(2).innerText()).trim()
      expect(denom, `第 ${i} 行的比率 ${rate} 旁边没有分母`).toMatch(/\d+\s*\/\s*\d+/)
    }
  })

  test('键盘也能开合 —— 它存在的理由就是悬停卡够不着的人', async ({
    authedPage: page,
  }) => {
    await openFirstTask(page)
    const details = page.locator('details').first()
    await details.locator('summary').focus()

    await page.keyboard.press('Enter')
    expect(await details.evaluate((d: HTMLDetailsElement) => d.open), '回车没展开').toBe(true)

    await page.keyboard.press(' ')
    expect(await details.evaluate((d: HTMLDetailsElement) => d.open), '空格没收起').toBe(false)
  })

  test('表格行数和图上的运行次数对得上', async ({ authedPage: page }) => {
    await openFirstTask(page)
    const caption = await page.getByText(/看数值（\d+ 次运行）/).innerText()
    const claimed = Number(caption.match(/(\d+)/)![1])

    await page.locator('details').first().locator('summary').click()
    const rows = await page.locator('details tbody tr').count()
    expect(rows, `摘要说 ${claimed} 次，表里却有 ${rows} 行`).toBe(claimed)
  })
})

test.describe('折叠提示条', () => {
  test('默认一行，展开后全文都在', async ({ authedPage: page }) => {
    await openFirstTask(page)
    // ⚠️ **不能用 filter({hasText:'展开'}) 定位** —— 那行字点一下就变成「收起」，
    // 定位器重新解析时会跳到另一条提示上，测试表现为「点了没反应」。踩过。
    // 用 data-notices-toggle 这个不随状态变的锚点。
    const bar = page.locator('[data-notices-toggle]').first()
    if ((await bar.count()) === 0) test.skip(true, '这个任务没有需要提示的口径问题')

    await expect(bar).toHaveAttribute('aria-expanded', 'false')
    const collapsedText = await bar.locator('xpath=..').innerText()

    await bar.click()
    await expect(bar).toHaveAttribute('aria-expanded', 'true')

    // 展开后的正文必须比摘要长得多 —— 折叠不能把内容折没了
    const expandedText = await bar.locator('xpath=..').innerText()
    expect(expandedText.length, '展开后没有多出内容').toBeGreaterThan(
      collapsedText.length * 2,
    )
  })

  test('折叠状态下也看得出有警告 —— 折叠不等于藏', async ({ authedPage: page }) => {
    await openFirstTask(page)
    const box = page.locator('[data-notices]').first()
    if ((await box.count()) === 0) test.skip(true, '这个任务没有需要提示的口径问题')

    // 最重的那一条的语气要带到摘要行上，否则一折叠就把警告的分量一起折掉了。
    // data-notices 的值就是那个语气，直接断言它，比反推颜色可靠。
    const worst = await box.getAttribute('data-notices')
    expect(['plain', 'alert', 'fault']).toContain(worst)

    if (worst !== 'plain') {
      // 非 plain 必须在收起状态下就有视觉标识
      const tone = await box.evaluate((el) => getComputedStyle(el).borderLeftColor)
      expect(tone, '有警告却没有任何视觉标识').not.toBe('rgba(0, 0, 0, 0)')
    }
  })
})

test.describe('首屏', () => {
  /**
   * 四个读数必须在折叠线以上。
   * 曾经四段口径说明占掉 307px，把读数全推到了 841px —— 视口才 759px 高，
   * 首屏一个数字都看不到。`kit/Notices` 就是为这个做的。
   */
  test('1280×800 下四个读数都在首屏内', async ({ authedPage: page }) => {
    await page.setViewportSize({ width: 1280, height: 800 })
    await openFirstTask(page)

    const firstReadoutTop = await page.evaluate(() => {
      for (const el of document.querySelectorAll('*')) {
        if (parseFloat(getComputedStyle(el).fontSize) < 30) continue
        const t = (el.textContent ?? '').trim()
        if (!/^\d+(\.\d+)?$/.test(t)) continue
        return Math.round(el.getBoundingClientRect().top)
      }
      return -1
    })

    expect(firstReadoutTop, '一个大号读数都没找到').toBeGreaterThan(0)
    expect(firstReadoutTop, '读数被推到折叠线以下了').toBeLessThan(800)
  })
})

test.describe('失败原因', () => {
  /**
   * 界面此前只说「另有 N 条采样失败」。七类失败的下一步完全不同 ——
   * `login_required` 要人去换登录态、`timeout` 等着就行 ——
   * 只报一个数字等于把「该做什么」留给读者猜。
   */
  test('失败提示要说清是哪一类、以及该做什么', async ({ authedPage: page }) => {
    await openFirstTask(page)

    // 样本列表在 tab 后面，默认显示的是命中矩阵
    const tab = page.getByRole('tab', { name: /样本列表/ })
    await tab.click()

    const notice = page.getByText(/另有 \d+ 条采样失败/)
    if ((await notice.count()) === 0) test.skip(true, '这次运行没有失败的采样')

    // 光有数字不够 —— 必须有分类和下一步
    const block = notice.locator('xpath=ancestor::p[1]')
    const text = await block.innerText()
    expect(text, '只报了数字，没说是哪一类失败').toMatch(
      /超时|被限流|登录态过期|平台没接|抽不出答案|worker|没认出原因|后端没给分类/,
    )
  })

  /**
   * 语气跟着**要不要人动手**走，不跟着条数走：
   * 24 条 timeout 会自愈，1 条 parse_error 得立刻处理。
   */
  test('全是能自愈的失败时不用红色吓人', async ({ authedPage: page }) => {
    await openFirstTask(page)
    await page.getByRole('tab', { name: /样本列表/ }).click()

    const notice = page.getByText(/另有 \d+ 条采样失败/)
    if ((await notice.count()) === 0) test.skip(true, '这次运行没有失败的采样')

    const block = notice.locator('xpath=ancestor::p[1]')
    const text = await block.innerText()
    const border = await block.evaluate((el) => getComputedStyle(el).borderLeftColor)

    // 只出现「超时 / 被限流」这两类 = 能自愈 = 不该是 fault 那档红色
    const selfHealingOnly = !/登录态过期|平台没接|抽不出答案|worker|没认出原因|后端没给分类/.test(
      text,
    )
    if (selfHealingOnly) {
      expect(border, '全是能自愈的失败却用了最重的语气').not.toBe('rgb(255, 107, 107)')
    } else {
      expect(border, '有要人动手的失败却没抬高语气').toBe('rgb(255, 107, 107)')
    }
  })
})

test.describe('三态与守卫', () => {
  test('表单初次加载失败要有出路 —— 不能只能离开页面', async ({ authedPage: page }) => {
    // 让 brands 请求失败，逼出 Fault
    await page.route('**/v1/brands**', (r) => r.abort('failed'))
    await page.goto('/tasks/new', { waitUntil: 'domcontentloaded' })

    const retry = page.getByRole('button', { name: /重试/ })
    await expect(retry, '加载失败了却没有重试按钮').toBeVisible()
  })

  test('有未保存改动时会拦住关闭页面', async ({ authedPage: page }) => {
    await page.goto('/brands', { waitUntil: 'networkidle' })
    await page.locator('a[href^="/brands/"]:not([href$="/new"])').first().click()
    await page.waitForLoadState('networkidle')

    // ⚠️ **不能用 `input[type="text"]`** —— 那几个 input 根本没写 type 属性，
    // 属性选择器要求属性存在才匹配，DOM 属性默认是 text 救不了它。
    // label 包着 input，隐式关联成立，按标签取最稳。
    const input = page.getByLabel('品牌名')
    await expect(input).toBeVisible()
    await input.fill('改了但没保存')

    // beforeunload 只拦整页卸载。这里直接问：有没有人注册了这个监听。
    // （拦不住站内跳转是**已知的取舍**，见 lib/use-unsaved-guard。）
    const guarded = await page.evaluate(() => {
      let fired = false
      const e = new Event('beforeunload', { cancelable: true })
      window.dispatchEvent(e)
      fired = e.defaultPrevented
      return fired
    })
    expect(guarded, '有未保存改动，但没有任何东西拦关闭页面').toBe(true)
  })
})
