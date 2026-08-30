import { test, expect, setTheme, trackFailedRequests } from './fixtures'

/**
 * 六个路由的冒烟 + 全站层级不变量。
 *
 * 断言的是**结构**不是数字 —— 生产数据每天在变，断言「12 次运行」明天就红了，
 * 而那不是回归。
 */

const ROUTES = [
  { path: '/tasks', h1: '检测任务' },
  { path: '/brands', h1: '品牌' },
  { path: '/users', h1: '用户管理' },
] as const

test.describe('路由冒烟', () => {
  for (const { path, h1 } of ROUTES) {
    test(`${path} 能打开，且只有一个页面级 h1`, async ({ authedPage: page }) => {
      const failed = trackFailedRequests(page)
      await page.goto(path, { waitUntil: 'networkidle' })

      // 「一页一个 h1、且在面板之外」是这一轮统一过的东西（kit/PageHead）。
      // 改版前 /brands 和 /users 整页没有 h1，标题塞在面板的 h2 里。
      const h1s = page.locator('h1')
      await expect(h1s).toHaveCount(1)
      await expect(h1s.first()).toHaveText(new RegExp(h1))

      // 空态/错误态不算通过 —— 那两个也会渲染出 h1
      await expect(page.getByText('加载失败')).toHaveCount(0)
      expect(failed, '有请求失败').toEqual([])
    })
  }

  test('任务详情：页头、图、读数三段都在', async ({ authedPage: page }) => {
    await page.goto('/tasks', { waitUntil: 'networkidle' })
    const firstTask = page.locator('a[href^="/tasks/"]:not([href$="/new"])').first()
    await firstTask.click()
    await page.waitForLoadState('networkidle')

    await expect(page).toHaveURL(/\/tasks\/\d+/)
    await expect(page.locator('h1')).toHaveCount(1)
    await expect(page.getByRole('img', { name: /次运行的提及率记录/ })).toBeVisible()
  })

  test('引用榜住在品牌之下 —— 不再是顶级入口', async ({ authedPage: page }) => {
    await page.goto('/brands', { waitUntil: 'networkidle' })

    // 侧栏只剩「检测任务 / 品牌」(+ 超管的「用户管理」)，没有「引用榜」
    const sidebarLinks = await page
      .locator('aside a[href^="/"]')
      .evaluateAll((els) => els.map((e) => e.getAttribute('href')))
    expect(sidebarLinks, '引用榜又回到顶级导航了').not.toContain('/citations')

    // 从品牌详情进得去，且 URL 把「这是谁的引用榜」写明白了
    await page.locator('a[href^="/brands/"]:not([href$="/new"])').first().click()
    await page.waitForLoadState('networkidle')
    await page.getByRole('link', { name: /引用榜/ }).click()
    await page.waitForLoadState('networkidle')
    await expect(page).toHaveURL(/\/brands\/\d+\/citations$/)
    await expect(page.locator('h1')).toHaveCount(1)
  })

  test('品牌列表只列监测对象，参照品牌不混在里面', async ({ authedPage: page }) => {
    await page.goto('/brands', { waitUntil: 'networkidle' })
    await expect(page.locator('tbody tr').first()).toBeVisible()

    // 列表里每一行都必须是监测对象：有任务或有竞品集。
    // 改版前这里平铺 17 行，其中 15 行是只作为对照存在的竞品。
    const rows = await page.locator('tbody tr').evaluateAll((trs) =>
      trs.map((tr) => {
        const td = tr.querySelectorAll('td')
        return {
          name: td[0]?.textContent?.trim() ?? '',
          competitors: td[4]?.textContent?.trim() ?? '',
          tasks: td[5]?.textContent?.trim() ?? '',
        }
      }),
    )
    expect(rows.length, '一个监测对象都没有').toBeGreaterThan(0)
    for (const r of rows) {
      const hasSomething = r.competitors !== '未配竞品' || r.tasks !== '还没建'
      expect(hasSomething, `「${r.name}」既没竞品也没任务，不该出现在监测对象列表里`).toBe(
        true,
      )
    }
  })

  test('新建任务只能选监测对象，且会告诉你提问集有多少条', async ({
    authedPage: page,
  }) => {
    await page.goto('/tasks/new', { waitUntil: 'networkidle' })
    const select = page.locator('select').first()
    await expect(select).toBeVisible()

    // 下拉里不能出现只作为竞品参照存在的品牌 —— 给「耐克」建任务几乎肯定是误操作
    const options = await select.locator('option').evaluateAll((els) =>
      els.map((e) => (e as HTMLOptionElement).value).filter(Boolean),
    )
    expect(options.length, '下拉是空的').toBeGreaterThan(0)

    const monitored = await page.evaluate(async () => {
      const [b, t] = await Promise.all([
        fetch('/v1/brands').then((r) => r.json()),
        fetch('/v1/tasks').then((r) => r.json()),
      ])
      const withTask = new Set(t.items.map((x: { brand_id: number }) => x.brand_id))
      const referenced = new Set<number>()
      for (const x of b.items) for (const c of x.competitor_ids) referenced.add(c)
      return b.items
        .filter(
          (x: { id: number; competitor_ids: number[] }) =>
            !(referenced.has(x.id) && !withTask.has(x.id) && x.competitor_ids.length === 0),
        )
        .map((x: { id: number }) => String(x.id))
    })
    expect(options.sort()).toEqual(monitored.sort())

    // 选一个品牌之后必须说清提问集有多少条 —— 它是任务的输入，却住在品牌页
    await select.selectOption(options[0])
    await expect(page.getByText(/条启用中的提问词|还没有启用中的提问词/)).toBeVisible()
  })

  test('两个核心实体互相到得了', async ({ authedPage: page }) => {
    // 任务 → 品牌。改版前品牌只是个徽章，点不动。
    await page.goto('/tasks', { waitUntil: 'networkidle' })
    await page.locator('a[href^="/tasks/"]:not([href$="/new"])').first().click()
    await page.waitForLoadState('networkidle')
    await page.locator('h1 a[href^="/brands/"]').first().click()
    await page.waitForLoadState('networkidle')
    await expect(page).toHaveURL(/\/brands\/\d+$/)

    // 品牌 → 任务，且落在**筛过的**列表上
    await page.getByRole('link', { name: /个任务/ }).click()
    await page.waitForLoadState('networkidle')
    await expect(page).toHaveURL(/\/tasks\?brand=\d+/)
    await expect(page.getByText(/只看「.+」的任务/)).toBeVisible()
    // 筛选态必须有出口
    await expect(page.getByRole('link', { name: '看全部' })).toBeVisible()
  })

  /**
   * 每个非顶级页面都要有一条回上一层的路，且**措辞一致**。
   * 改版前三页各写了一份、两种句式（「← 品牌列表」vs「← 回到品牌」），
   * 另有三页干脆没有 —— 包括两个 /new，它们连 h1 都没有。
   */
  const NESTED = ['/tasks/new', '/brands/new'] as const
  for (const path of NESTED) {
    test(`${path} 有页面级 h1，也有回上一层的路`, async ({ authedPage: page }) => {
      await page.goto(path, { waitUntil: 'networkidle' })
      await expect(page.locator('h1')).toHaveCount(1)

      // ⚠️ **不能按箭头定位**：箭头是 aria-hidden，可访问名里没有它，
      // `getByRole('link', { name: /^←/ })` 永远匹配不到。用 data-page-back。
      const back = page.locator('[data-page-back]').first()
      await expect(back, '这一页没有回上一层的路').toBeVisible()
      // 只写目的地的名字，不写「回到」「返回」—— 箭头已经说了方向
      expect(await back.innerText()).not.toMatch(/回到|返回/)
    })
  }

  test('任务详情和引用榜也各有一条回上一层的路', async ({ authedPage: page }) => {
    await page.goto('/tasks', { waitUntil: 'networkidle' })
    await page.locator('a[href^="/tasks/"]:not([href$="/new"])').first().click()
    await page.waitForLoadState('networkidle')
    const back = page.locator('[data-page-back]').first()
    await expect(back).toBeVisible()
    await back.click()
    await page.waitForLoadState('networkidle')
    await expect(page).toHaveURL(/\/tasks$/)
  })

  test('品牌详情能从列表点进去', async ({ authedPage: page }) => {
    await page.goto('/brands', { waitUntil: 'networkidle' })
    await page.locator('a[href^="/brands/"]:not([href$="/new"])').first().click()
    await page.waitForLoadState('networkidle')
    await expect(page).toHaveURL(/\/brands\/\d+/)
    await expect(page.locator('h1')).toHaveCount(1)
  })
})

test.describe('口径不变量', () => {
  /**
   * **比率永远和分母同框。**
   *
   * 这是这个产品可信度的来源（README §3.1）：一个孤零零的「66.7%」说不清
   * 它是 2/3 还是 12/18。`ReadoutRate` 在类型层面强制要 m 和 n，这里从
   * 渲染结果再钉一次 —— 类型挡不住有人写个 `<div>66.7%</div>`。
   */
  test('每个大号比率读数下面都有 m / n', async ({ authedPage: page }) => {
    await page.goto('/tasks', { waitUntil: 'networkidle' })
    await page.locator('a[href^="/tasks/"]:not([href$="/new"])').first().click()
    await page.waitForLoadState('networkidle')

    // ⚠️ `networkidle` **不等于读数已经渲染**。读数来自 mount 之后才发的
    // `/v1/counts`，客户端跳转时 networkidle 可能在那之前就 resolve 了，
    // 于是 evaluate 跑在骨架屏上、一个读数都找不到。踩过。
    // 直接轮询「读数出现了没有」，这才是这条用例真正依赖的东西。
    await expect
      .poll(
        () =>
          page.evaluate(
            () =>
              [...document.querySelectorAll('*')].filter(
                (el) =>
                  parseFloat(getComputedStyle(el).fontSize) >= 30 &&
                  /^\d+(\.\d+)?\s*%?$/.test((el.textContent ?? '').trim()),
              ).length,
          ),
        {
          // 30s 不是随手写的：这条等的是「dev server 冷编译这条路由 +
          // 一趟打到线上的 API」。点击若发生在 hydration 之前，<Link> 还是
          // 普通 <a>，会走整页导航、让 Next 从头编译 —— 10s 会偶发不够。
          // 手动实测热路由是 1.8s。
          timeout: 30_000,
          message: '等了很久也没有任何大号读数渲染出来',
        },
      )
      .toBeGreaterThan(0)

    const readouts = await page.evaluate(() => {
      const out: { label: string; value: string; denom: string }[] = []
      for (const el of document.querySelectorAll('*')) {
        const cs = getComputedStyle(el)
        if (parseFloat(cs.fontSize) < 30) continue
        const txt = (el.textContent ?? '').trim()
        if (!/^\d+(\.\d+)?\s*%?$/.test(txt)) continue
        // 读数块 = 值的父节点；分母是同一块里的最后一行
        const block = el.parentElement
        out.push({
          label: block?.firstElementChild?.textContent?.trim() ?? '',
          value: txt,
          denom: block?.lastElementChild?.textContent?.trim() ?? '',
        })
      }
      return out
    })

    expect(readouts.length, '一个读数都没找到').toBeGreaterThan(0)
    for (const r of readouts) {
      if (!r.value.includes('%') && !/^\d+$/.test(r.value)) continue
      expect(
        r.denom,
        `读数「${r.label} = ${r.value}」旁边没有分母，只有「${r.denom}」`,
      ).toMatch(/\d/)
    }
  })

  /** 算不出来显示 —，不显示 0 —— null ≠ 0 是这个产品的第一条口径。 */
  test('页面上不出现「0%」冒充「算不出来」', async ({ authedPage: page }) => {
    // 引用榜现在住在品牌之下
    await page.goto('/brands', { waitUntil: 'networkidle' })
    const href = await page
      .locator('a[href^="/brands/"]:not([href$="/new"])')
      .first()
      .getAttribute('href')
    await page.goto(`${href}/citations`, { waitUntil: 'networkidle' })
    const zeroWithoutDenom = await page.evaluate(() => {
      const bad: string[] = []
      for (const el of document.querySelectorAll('*')) {
        if (el.children.length) continue
        const t = (el.textContent ?? '').trim()
        if (t !== '0.0%' && t !== '0%') continue
        // 真的是 0 的话，同一个读数块里必须有 0 / n 这样的分母佐证。
        // ⚠️ **不能用 `closest('div')`** —— 值自己就包在一个只装值的 div 里
        // （`.bucketValue` 之类），框到的文字就是「0.0%」本身，永远判成没分母。
        // 往上找几层，直到某一层能看到分母为止。
        let ok = false
        let scope: Element | null = el
        let text = ''
        for (let up = 0; up < 4 && scope; up++) {
          scope = scope.parentElement
          text = scope?.textContent ?? ''
          if (/\d+\s*\/\s*\d+/.test(text)) {
            ok = true
            break
          }
        }
        if (!ok) bad.push(text.slice(0, 60) || t)
      }
      return bad
    })
    expect(zeroWithoutDenom, '有 0% 没带分母 —— 分不清「真是 0」还是「算不出来」').toEqual(
      [],
    )
  })
})

test.describe('明暗两档', () => {
  for (const { path } of ROUTES) {
    test(`${path} 两档都没有文字对比度不足`, async ({ authedPage: page }) => {
      await page.goto(path, { waitUntil: 'networkidle' })
      for (const theme of ['dark', 'light'] as const) {
        await setTheme(page, theme)
        const fails = await page.evaluate(() => {
          // ⚠️ 颜色的计算值有四种写法：#rgb / #rrggbbaa / rgb() / color(srgb 0-1)。
          // 之前两次量错都是 parser 只认了其中一种 —— alpha 丢了，或把 0-1
          // 当成 0-255，结果一堆假阳性。
          const C = (s: string) => {
            s = (s || '').trim()
            if (s.startsWith('#')) {
              let h = s.slice(1)
              if (h.length === 3 || h.length === 4) h = [...h].map((x) => x + x).join('')
              const n = (i: number) => parseInt(h.slice(i, i + 2), 16)
              return { c: [n(0), n(2), n(4)], a: h.length === 8 ? n(6) / 255 : 1 }
            }
            const f = s.startsWith('color(')
            const m = (s.match(/[\d.]+/g) || []).map(Number)
            if (!m.length) return null
            const v = m.slice(f ? 1 : 0, (f ? 1 : 0) + 3)
            const al = s.match(/\/\s*([\d.]+)\s*\)/)
            return {
              c: f ? v.map((x) => x * 255) : v,
              a: al ? +al[1] : m.length > (f ? 4 : 3) ? m[f ? 4 : 3] : 1,
            }
          }
          const lum = (c: number[]) => {
            const [r, g, b] = c.map((v) => {
              v /= 255
              return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4
            })
            return 0.2126 * r + 0.7152 * g + 0.0722 * b
          }
          const bgOf = (el: Element): number[] => {
            let e: Element | null = el
            while (e) {
              const b = getComputedStyle(e).backgroundColor
              const p = C(b)
              if (p && p.a > 0.9 && b !== 'rgba(0, 0, 0, 0)') return p.c
              e = e.parentElement
            }
            return C(getComputedStyle(document.body).backgroundColor)?.c ?? [255, 255, 255]
          }
          const out: string[] = []
          for (const el of document.querySelectorAll('*')) {
            const t = [...el.childNodes]
              .filter((n) => n.nodeType === 3 && n.textContent!.trim())
              .map((n) => n.textContent!.trim())
              .join('')
            if (!t) continue
            const cs = getComputedStyle(el)
            if (cs.visibility === 'hidden' || cs.display === 'none' || +cs.opacity < 0.1)
              continue
            const r = el.getBoundingClientRect()
            if (!r.width || !r.height) continue
            const fg = C(cs.color)
            if (!fg) continue
            const bg = bgOf(el)
            const eff = fg.c.map((v, i) => v * fg.a + bg[i] * (1 - fg.a))
            const [x, y] = [lum(eff), lum(bg)]
            const cr = (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05)
            const sz = parseFloat(cs.fontSize)
            const need = sz >= 24 || (sz >= 18.66 && +cs.fontWeight >= 700) ? 3 : 4.5
            if (cr < need) out.push(`${t.slice(0, 20)} ${cr.toFixed(2)} < ${need}`)
          }
          return out
        })
        expect(fails, `${theme} 档对比度不足`).toEqual([])
      }
    })
  }
})
