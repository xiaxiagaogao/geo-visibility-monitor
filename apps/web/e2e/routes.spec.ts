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
  { path: '/citations', h1: '引用榜' },
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
    await page.goto('/citations', { waitUntil: 'networkidle' })
    const zeroWithoutDenom = await page.evaluate(() => {
      const bad: string[] = []
      for (const el of document.querySelectorAll('*')) {
        if (el.children.length) continue
        const t = (el.textContent ?? '').trim()
        if (t !== '0.0%' && t !== '0%') continue
        // 真的是 0 的话，同一块里必须有 0 / n 这样的分母佐证
        const block = el.closest('div')?.textContent ?? ''
        if (!/\d+\s*\/\s*\d+/.test(block)) bad.push(block.slice(0, 60))
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
