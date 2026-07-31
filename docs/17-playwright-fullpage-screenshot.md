# Playwright 全页面截图功能说明

## 0. 本项目（geo-demo）实际用法

**截图在哪里抓？**  
在 **VPS 的 `geo-crawler` 容器**里，用 Playwright 无头 Chromium 抓，**不是**你 Mac 本机 Chrome。

**为什么不能直接对 DeepSeek 页面 `full_page=True`？**  
DeepSeek 聊天 UI 有左侧历史、底部输入框、内部滚动容器。直接整页截图会得到「侧栏+半截回答+输入框」——就像 QA 里 #17 那种坏证据。

**当前策略（干净证据）：**

1. 用 Playwright locator 从 `.ds-markdown` 抽出**完整回答 HTML**（表格/列表保留）
2. `context.new_page()` + `set_content` 渲染一张**深色卡片**（问题气泡 + 回答正文）
3. 对这张独立页 `screenshot(full_page=True)`  
4. 失败才 fallback：隐藏侧栏/输入框 → 撑开内部 scroller → live `full_page`

代码：`apps/api/app/providers/deepseek_web.py` → `_capture_answer_evidence`  
产物：`/data/screenshots/deepseek_*.png`（volume `crawl_data`）  
QA 预览：`/qa/media/screenshots/{filename}`

**部署注意：** `post-receive` 默认会 rebuild api；crawler 有容器时一并 rebuild。代码进 worktree ≠ 进镜像，必须 rebuild crawler。

---

> 适用于无头 Chromium（Headless Chromium）场景  
> 实现真正的**全量页面截图**（包含滚动条范围内的所有内容），而非仅可视区域截图。

---

## 1. 功能概述

Playwright 默认的 `page.screenshot()` 只会截取当前视口（viewport）可见的内容。  
通过设置 `fullPage: true`（Python 中为 `full_page=True`），Playwright 会：

1. 计算整个页面的滚动高度（`document.documentElement.scrollHeight`）
2. 临时扩展渲染区域
3. 自动滚动并拼接生成完整的长图

最终得到的是一张包含页面顶部到最底部所有内容的截图，适合文档存档、页面对比、视觉回归测试等场景。

---

## 2. 基本用法

### 2.1 Node.js / TypeScript

```js
const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({
    headless: true, // 无头模式
  });

  const page = await browser.newPage();

  // 建议设置固定视口宽度，保证截图一致性
  await page.setViewportSize({ width: 1280, height: 800 });

  await page.goto('https://example.com', {
    waitUntil: 'networkidle', // 等待网络基本空闲
  });

  // 全页面截图（核心参数）
  await page.screenshot({
    path: 'fullpage.png',
    fullPage: true,           // 开启全页面截图
  });

  await browser.close();
})();
```

### 2.2 Python

```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1280, "height": 800})

    page.goto("https://example.com", wait_until="networkidle")

    # 全页面截图
    page.screenshot(
        path="fullpage.png",
        full_page=True          # 开启全页面截图
    )

    browser.close()
```

---

## 3. 核心参数说明

| 参数              | 类型     | 默认值   | 说明                                                                 |
|-------------------|----------|----------|----------------------------------------------------------------------|
| `fullPage` / `full_page` | boolean  | `false`  | **关键参数**。设为 `true` 时截取整个可滚动页面                       |
| `path`            | string   | -        | 保存路径（不传则返回 Buffer）                                        |
| `type`            | string   | `'png'`  | 图片格式，可选 `'png'` 或 `'jpeg'`                                   |
| `quality`         | number   | -        | 仅 `jpeg` 有效，取值 0-100                                           |
| `omitBackground`  | boolean  | `false`  | 透明背景（仅 `png` 有效，对 fullPage 支持有限）                      |
| `clip`            | object   | -        | 指定裁剪区域（与 fullPage 互斥）                                     |

---

## 4. 重要注意事项与最佳实践

### 4.1 懒加载（Lazy Load）内容处理

很多现代网站的图片、模块只有滚动到可视区域才会真正加载。  
单纯使用 `fullPage: true` 可能导致底部内容缺失。

**推荐做法：先滚动触发懒加载，再截图**

```js
// 平滑滚动到底部，触发懒加载
await page.evaluate(async () => {
  await new Promise((resolve) => {
    let totalHeight = 0;
    const distance = 400; // 每次滚动距离
    const timer = setInterval(() => {
      const scrollHeight = document.body.scrollHeight;
      window.scrollBy(0, distance);
      totalHeight += distance;

      if (totalHeight >= scrollHeight - window.innerHeight) {
        clearInterval(timer);
        resolve();
      }
    }, 150);
  });
});

// 可选：滚回顶部
await page.evaluate(() => window.scrollTo(0, 0));
await page.waitForTimeout(500); // 给页面一点渲染时间

// 再执行全页面截图
await page.screenshot({ path: 'fullpage.png', fullPage: true });
```

### 4.2 超长页面高度限制

Chromium 在 headless 模式下对单张截图高度有限制（通常约 **16384 像素**）。  
超过此高度时，截图可能被截断或出现重复内容。

**应对方案：**
- 分段截图后自行拼接
- 降低视口宽度（减少内容高度）
- 使用第三方长图服务

### 4.3 固定定位（fixed / sticky）元素

全页面截图过程中，固定头部、侧边栏、悬浮按钮等元素可能会出现：
- 重复显示
- 位置错乱
- 覆盖其他内容

这是浏览器渲染机制导致的正常现象，目前没有完美的通用解决方案。

### 4.4 视口设置建议

为了保证截图结果稳定、可复现，建议固定视口宽度：

```js
await page.setViewportSize({ width: 1280, height: 800 });
// 或
const context = await browser.newContext({
  viewport: { width: 1280, height: 800 },
});
```

高度可以随意，因为 `fullPage: true` 会忽略视口高度。

---

## 5. 进阶用法示例

### 5.1 截图并返回 Buffer（不落盘）

```js
const buffer = await page.screenshot({ fullPage: true });
// 可直接上传、转 base64 或进行图像处理
console.log(buffer.toString('base64'));
```

### 5.2 JPEG 格式 + 质量控制

```js
await page.screenshot({
  path: 'fullpage.jpg',
  fullPage: true,
  type: 'jpeg',
  quality: 85,
});
```

### 5.3 结合 Playwright Test 的视觉回归

```js
import { test, expect } from '@playwright/test';

test('全页面视觉对比', async ({ page }) => {
  await page.goto('https://example.com');
  await expect(page).toHaveScreenshot({
    fullPage: true,
  });
});
```

---

## 6. 常见问题 FAQ

**Q1：为什么截出来的图还是只有一屏？**  
A：确认是否正确传入了 `fullPage: true`（注意大小写和 Python 的下划线写法）。

**Q2：底部内容缺失怎么办？**  
A：大概率是懒加载问题，参考第 4.1 节先滚动触发加载。

**Q3：截图特别慢？**  
A：超长页面需要滚动拼接，属于正常现象。可适当减少等待时间或优化页面加载策略。

**Q4：headless 和 headed 模式下截图不一致？**  
A：字体渲染、抗锯齿等会有细微差异，建议统一在 CI 环境中使用 headless 模式生成基准图。

**Q5：能否截取某个 iframe 的全页面？**  
A：需要先切换到对应 frame，再对该 frame 的 page 对象执行截图。

---

## 7. 快速参考

```js
// 最简全页面截图
await page.screenshot({ path: 'full.png', fullPage: true });

// 推荐完整写法
await page.goto(url, { waitUntil: 'networkidle' });
await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight)); // 触发懒加载
await page.waitForTimeout(1000);
await page.screenshot({ path: 'full.png', fullPage: true });
```

---

**文档版本**：2026-07-31  
**适用 Playwright 版本**：1.40+（推荐最新稳定版）  
**浏览器**：Chromium / Chrome（headless 模式）

如有其他特殊场景需求（如超长页面分段拼接、移动端全屏截图等），可继续补充说明。
