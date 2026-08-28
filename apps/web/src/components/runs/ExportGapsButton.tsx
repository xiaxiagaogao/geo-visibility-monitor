'use client'

import { Button } from '@/components/kit'
import { safeFileName, toCsv } from '@/lib/l3/csv'

/**
 * 把已经算好的行下成一个 CSV 文件。
 *
 * 只吃 props —— 行的内容在 `lib/l3/gap-export`，转义与 BOM 在 `lib/l3/csv`，
 * 这里只负责「变成一个文件」。
 *
 * **不经过后端。** 数据已经在页面上了，为导出加一个端点等于把缺口判级
 * 逻辑在后端重写一遍（后端没有 gap 这个概念）—— 那是两份定义。
 */
export function ExportGapsButton({
  rows,
  fileName,
  disabled,
}: {
  rows: (string | number)[][]
  fileName: string
  disabled?: boolean
}) {
  function download() {
    const blob = new Blob([toCsv(rows)], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = safeFileName(fileName)
    document.body.appendChild(a)
    a.click()
    a.remove()
    // 不撤销会一直占着内存直到页面卸载 —— 这个页面用户可能开一整天
    URL.revokeObjectURL(url)
  }

  return (
    <Button onClick={download} disabled={disabled}>
      导出 CSV
    </Button>
  )
}
