#!/usr/bin/env bash
# 重新生成思源黑体 SC（静态 wght=600）的中文子集。
#
# 什么时候要跑：**界面上新增了汉字文案之后。**
# 子集只含仓库里出现过的字；漏掉的字会单独掉回系统字，一个词里两种字形。
#
# 用法：bash scripts/fonts/build-cjk-subset.sh
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT="$REPO/apps/web/public/fonts/NotoSansSC-600-subset.woff2"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# 可变字重 TTF（17.7 MB），下面会先固化到 wght=600 再子集化 ——
# 中文字形的体积压在轮廓上不在轴上：全轴子集 362 KB、限轴 500–700 仍 322 KB，
# 而单一 600 只要 193 KB。标题的粗细层级靠字号与字距做，不靠字重插值。
URL="https://raw.githubusercontent.com/google/fonts/main/ofl/notosanssc/NotoSansSC%5Bwght%5D.ttf"

echo "→ 扫描仓库里用到的汉字"
python3 - "$REPO" "$WORK/subset.txt" <<'PY'
import pathlib, sys
repo, out = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])

chars = set()
sources = list((repo / 'apps/web/src').rglob('*')) + [
    repo / 'PRODUCT.md', repo / 'apps/web/README.md', repo / 'docs/API.md',
]
for p in sources:
    if p.is_file() and p.suffix in ('.tsx', '.ts', '.css', '.md'):
        for ch in p.read_text(encoding='utf-8', errors='ignore'):
            if '一' <= ch <= '鿿' or '㐀' <= ch <= '䶿':
                chars.add(ch)

# 标点、量纲符号、序号、箭头 —— 界面上会用到但不一定已经写进源码
chars.update('　、。〈〉《》「」『』【】〔〕〖〗・ー―‐‑–—…‥‧※¶§†‡°′″℃％‰'
             '±×÷≈≠≤≥∞√∑∫∂∆∏πµΩ①②③④⑤⑥⑦⑧⑨⑩⓪↑↓←→↔⇄✓✗∅'
             '－＋＝／＼｜～！？：；，．０１２３４５６７８９“”‘’（）')
chars.update(chr(c) for c in range(0x20, 0x7f))

out.write_text(''.join(sorted(chars)), encoding='utf-8')
print(f'  子集字符数：{len(chars)}')
PY

echo "→ 取原始可变字体"
curl -fsSL --max-time 300 -o "$WORK/NotoSansSC-VF.ttf" "$URL"

echo "→ 建一次性 venv 装 fonttools"
python3 -m venv "$WORK/.v" >/dev/null
"$WORK/.v/bin/pip" -q install fonttools brotli

echo "→ 固化到 wght=600"
"$WORK/.v/bin/fonttools" varLib.instancer "$WORK/NotoSansSC-VF.ttf" wght=600 \
  -o "$WORK/NotoSansSC-600.ttf" >/dev/null

echo "→ 子集化"
"$WORK/.v/bin/pyftsubset" "$WORK/NotoSansSC-600.ttf" \
  --text-file="$WORK/subset.txt" \
  --flavor=woff2 \
  --layout-features='*' \
  --output-file="$OUT"

printf '✓ %s  (%s)\n' "$OUT" "$(du -h "$OUT" | cut -f1)"
