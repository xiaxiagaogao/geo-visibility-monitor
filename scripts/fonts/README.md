# 自托管字体

三个文件，共约 188 KB，全部放在 `apps/web/public/fonts/`，由
`apps/web/src/styles/fonts.css` 声明。**不走 Google Fonts CDN** —— 生产在国内访问不稳，
且外部字体请求会把访问者的 IP 泄给第三方。

| 文件 | 来源 | 授权 | 用途 |
|---|---|---|---|
| `MartianMono-latin.woff2`<br>`MartianMono-latin-ext.woff2` | [Martian Mono](https://github.com/evilmartians/mono) v6（Google Fonts 托管的 latin / latin-ext 子集，可变字重 300–800） | SIL OFL 1.1 | **仪器的声音**：所有数字、比率、代号、刻度读数、面板小标 |
| `SmileySans-Oblique-subset.woff2` | [得意黑 Smiley Sans](https://github.com/atelier-anchor/smiley-sans) v2.0.1，**子集化后 148 KB**（原 1.1 MB） | SIL OFL 1.1 | 中文**展示字**：字标、页标题、面板标题。仅此三处 |

中文正文、提问词原文、AI 回答原文一律走**系统字栈**（PingFang SC / Noto Sans SC / 微软雅黑）——
那部分内容是无界的，不可能子集化，硬塞一个 1.1 MB 的 CJK woff2 是拿访问者的流量买设计感。

---

## ⚠️ 改了界面文案就要重跑子集

得意黑那个文件**只包含仓库里已经出现过的汉字**（当前 1239 个字符，含标点与 ASCII）。
新写一个界面标签用到了子集外的字，那个字会**单独掉回系统字**，一个词里两种字形，很明显。

```bash
bash scripts/fonts/build-cjk-subset.sh
```

脚本会重新扫描 `apps/web/src` + `PRODUCT.md` + 两份文档里的全部汉字，重新生成子集并覆盖。
需要 Python 3 与网络（首次会下原始字体并在 `/tmp` 建一次性 venv 装 `fonttools`）。

**为什么不干脆全量打包**：全量 1.1 MB。这个站的首屏本来就要拉四路接口，
再加 1.1 MB 字体是把「设计上讲究」变成「用起来更慢」，方向反了。
