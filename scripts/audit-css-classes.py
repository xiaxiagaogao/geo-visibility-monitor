#!/usr/bin/env python3
"""
查出所有指向**不存在的 CSS Module 类**的 className。

为什么需要这个：CSS Modules 查不到键**不报错**，返回 `undefined`，
className 落成空字符串 —— 元素以浏览器默认样式渲染，没有任何提示。
tsc 也拦不住，因为那个导入对象的类型是 `Record<string, string>`。

2026-08-29 第一次跑，一次找出 7 个：`kit.rowLink`（四处行内链接在暗色底上
显示成浏览器默认的蓝紫下划线）、`kit.numeric`、`kit.dense`、
`runs.panelStack` / `taskHead` / `taskTitle` / `taskMeta`。

用法：python3 scripts/audit-css-classes.py     # 有命中时退出码 1
"""
import collections
import pathlib
import re
import sys

SRC = pathlib.Path(__file__).resolve().parent.parent / 'apps/web/src'


def main() -> int:
    defs = {
        c.name: set(re.findall(r'^\.([A-Za-z][\w-]*)', c.read_text(encoding='utf-8'), re.M))
        for c in SRC.rglob('*.module.css')
    }

    missing: dict[str, list[str]] = collections.defaultdict(list)
    for tsx in SRC.rglob('*.tsx'):
        src = tsx.read_text(encoding='utf-8')
        alias = dict(re.findall(r"import\s+(\w+)\s+from\s+'([^']*\.module\.css)'", src))
        # `kit` 是从桶文件再导出的样式对象，不是直接 import 的 css module
        if re.search(r"\bkit\b[^\n]*from '@/components/kit'", src) or re.search(
            r'^\s*kit,\s*$', src, re.M
        ):
            alias.setdefault('kit', 'kit.module.css')

        for a, path in alias.items():
            name = path.split('/')[-1]
            if name not in defs:
                continue
            for m in re.finditer(rf'\b{a}\.([A-Za-z]\w*)\b', src):
                key = m.group(1)
                # `runs.module.css` 这种 import 字面量会被上面的正则扫到
                if key == 'module' or key in defs[name]:
                    continue
                missing[f'{name}.{key}'].append(str(tsx.relative_to(SRC)))

    for key, files in sorted(missing.items()):
        print(f'  ✗ {key}  ←  {", ".join(sorted(set(files)))}')
    print(f'—— 引用了不存在的类：{len(missing)} 处')
    return 1 if missing else 0


if __name__ == '__main__':
    sys.exit(main())
