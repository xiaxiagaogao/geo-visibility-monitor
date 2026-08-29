import { defineConfig } from 'vitest/config'

/**
 * 单元测试（`lib/l3/` 的纯函数）。
 *
 * **`include` 必须收窄到 `*.test.ts`。** vitest 默认还收 `*.spec.ts`，
 * 而端到端用的是 Playwright 的 `test.describe`，被 vitest 加载会直接报
 * 「Playwright Test did not expect test.describe() to be called here」。
 * 两个 runner 靠**文件后缀**分家：`.test.ts` 归 vitest，`.spec.ts` 归 playwright。
 */
export default defineConfig({
  test: {
    include: ['src/**/*.test.ts'],
  },
})
