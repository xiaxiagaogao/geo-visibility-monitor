#!/usr/bin/env bash
# 重新生成得意黑的中文子集。
#
# 什么时候要跑：**界面上新增了汉字文案之后。**
# 子集只含仓库里出现过的字；漏掉的字会单独掉回系统字，一个词里两种字形。
#
# 用法：bash scripts/fonts/build-cjk-subset.sh
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT="$REPO/apps/web/public/fonts/SmileySans-Oblique-subset.woff2"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

VERSION="v2.0.1"
URL="https://github.com/atelier-anchor/smiley-sans/releases/download/${VERSION}/smiley-sans-${VERSION}.zip"

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

echo "→ 取原始字体 $VERSION"
curl -fsSL --max-time 180 -o "$WORK/ss.zip" "$URL"
unzip -oq "$WORK/ss.zip" -d "$WORK/ss"

echo "→ 建一次性 venv 装 fonttools"
python3 -m venv "$WORK/.v" >/dev/null
"$WORK/.v/bin/pip" -q install fonttools brotli

echo "→ 子集化"
"$WORK/.v/bin/pyftsubset" "$WORK/ss/SmileySans-Oblique.ttf" \
  --text-file="$WORK/subset.txt" \
  --flavor=woff2 \
  --layout-features='*' \
  --output-file="$OUT"

printf '✓ %s  (%s)\n' "$OUT" "$(du -h "$OUT" | cut -f1)"
