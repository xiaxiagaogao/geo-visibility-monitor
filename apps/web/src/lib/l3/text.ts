/**
 * 文本的**码点**口径 —— 跨语言索引对齐。
 *
 * 后端所有和「位置 / 长度」有关的数字都是 Python 侧算的，
 * 而 Python 的字符串索引是**码点**：
 *
 *   · `Mention.first_offset`         —— 命中在正文里的下标
 *   · `RawResponseSummary.text_length` —— Postgres `length()` 给的字符数
 *
 * JS 的 `String.prototype.length` 与 `.slice()` 都按 **UTF-16 单元**。
 * 一个 🏃 在 Python 里算 1、在 JS 里算 2 —— 正文里有一个 emoji，
 * 两边就开始对不上。
 *
 * **这个 bug 真的上过线**：2026-08-12 部署后冒烟在生产数据上抓到，
 * 某条回答含 4 个 emoji（810 码点 / 814 UTF-16 单元），`Nike` 被切成了
 * `如Nik`。证据页的自检拦住了它（对不上就不画、改报告警），所以没画错，
 * 但含 emoji 的回答一律没有高亮。
 *
 * 放在独立模块而不是 `evidence.ts` 里：`samples.ts` 也要用它，
 * 让 samples 去 import evidence 是把两个不相干的概念拴在一起，
 * 而各写一份就又是「同一个东西两处定义」。
 *
 * 纯函数，不碰 fetch 与 React。
 */

/** 按码点拆分。**不是 `split('')`** —— 那个按 UTF-16 单元拆，会把 emoji 劈成两半 */
export function toCodePoints(text: string): string[] {
  return Array.from(text)
}

/** 码点数。凡要和后端给的长度/下标比较，都用这个，别用 `.length` */
export function codePointLength(text: string): number {
  return toCodePoints(text).length
}
