/**
 * CSV 生成（P2-04）。
 *
 * 生成放在前端不是图省事：**缺口判级（`findGaps`）只在前端存在**，
 * 后端没有 gap 这个概念。加一个导出端点就要把那套判级重写一遍 ——
 * 那是「同一个东西两份定义」，而两份迟早只改一边。
 *
 * 这个文件解决四个具体的坑，每个都真的会咬人：
 *
 *   1. **公式注入**（安全问题，见 `neutralizeFormula`）
 *   2. **中文乱码** —— Excel 不认无 BOM 的 UTF-8
 *   3. **字段里的逗号 / 引号 / 换行** —— RFC 4180 转义
 *   4. **Excel 把 `3/5` 当成日期** —— 所以调用方要拆成两列，别拼成分数串
 *
 * 纯函数，不碰 fetch 与 React（下载动作在组件里）。
 */

/**
 * 中和公式注入。
 *
 * **这是安全问题，不是格式问题。** 提问词由运营自由输入，而导出的文件是拿去
 * 发给推流团队、在**别人的 Excel 里**打开的。一条以 `=` 开头的提问词
 * （`=HYPERLINK("http://evil","季度报表")`）会在对方机器上变成可点的钓鱼链接，
 * 而表格看起来完全正常。
 *
 * 处理：给 `= + - @` 以及制表/回车开头的值前面补一个单引号 ——
 * Excel 把它当成「强制文本」的标记并且不显示出来，其它工具则原样看到一个引号。
 * 两种结果都比执行公式好。
 */
export function neutralizeFormula(value: string): string {
  return /^[=+\-@\t\r]/.test(value) ? `'${value}` : value
}

/** RFC 4180 转义：含逗号、引号、换行的字段要整体加引号，内部引号翻倍 */
export function escapeCsvField(value: string | number | null | undefined): string {
  const raw = value === null || value === undefined ? '' : String(value)
  const safe = neutralizeFormula(raw)
  return /[",\r\n]/.test(safe) ? `"${safe.replace(/"/g, '""')}"` : safe
}

/**
 * 行数组 → CSV 文本。
 *
 * **带 UTF-8 BOM。** 不带的话 Excel 会按本地代码页解释，中文全是乱码 ——
 * 而这份文件的读者就是拿 Excel 打开的人。代价是某些命令行工具会看到
 * 开头多三个字节，两害相权取其轻。
 *
 * 换行用 CRLF，同样是为了 Excel。
 */
export function toCsv(rows: (string | number | null | undefined)[][]): string {
  const body = rows.map((r) => r.map(escapeCsvField).join(',')).join('\r\n')
  return `﻿${body}\r\n`
}

/**
 * 文件名里不能出现的字符 —— 路径分隔符与 Windows 保留字符。
 *
 * 任务名是用户输入的，直接拼进文件名会拼出 `缺口_A/B_run54.csv` 这种
 * 在下载时被截断或失败的名字。
 */
export function safeFileName(name: string): string {
  return name.replace(/[\\/:*?"<>|]/g, '_').replace(/\s+/g, ' ').trim() || 'export'
}
