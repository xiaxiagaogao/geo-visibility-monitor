# 自托管字体

三个文件，共约 188 KB，全部放在 `apps/web/public/fonts/`，由
`apps/web/src/styles/fonts.css` 声明。**不走 Google Fonts CDN** —— 生产在国内访问不稳，
且外部字体请求会把访问者的 IP 泄给第三方。

| 文件 | 来源 | 授权 | 用途 |
|---|---|---|---|
| `Geist-latin.woff2`<br>`Geist-latin-ext.woff2` | [Geist](https://vercel.com/font) v5（Google Fonts 的 latin / latin-ext 子集，可变字重 100–900） | SIL OFL 1.1 | 拉丁展示与正文 |
| `GeistMono-latin.woff2`<br>`GeistMono-latin-ext.woff2` | Geist Mono v6，同上 | SIL OFL 1.1 | **数据**：数字、比率、代号、时间戳、列头 |
| `NotoSansSC-600-subset.woff2` | [思源黑体 SC](https://github.com/google/fonts/tree/main/ofl/notosanssc)，**静态 wght=600 + 子集化后 193 KB**（原可变 17.7 MB） | SIL OFL 1.1 | 中文**展示字**：字标、页标题、面板标题。仅此三处 |

中文正文、提问词原文、AI 回答原文一律走**系统字栈**（PingFang SC / Noto Sans SC / 微软雅黑）——
那部分内容是无界的，不可能子集化，硬塞一个 1.1 MB 的 CJK woff2 是拿访问者的流量买设计感。

---

## ⚠️ 改了界面文案就要重跑子集

思源那个文件**只包含仓库里已经出现过的汉字**（当前 1310 个字符，含标点与 ASCII）。
新写一个界面标签用到了子集外的字，那个字会**单独掉回系统字**，一个词里两种字形，很明显。

```bash
bash scripts/fonts/build-cjk-subset.sh
```

脚本会重新扫描 `apps/web/src` + `PRODUCT.md` + 两份文档里的全部汉字，重新生成子集并覆盖。
需要 Python 3 与网络（首次会下原始字体并在 `/tmp` 建一次性 venv 装 `fonttools`）。

**为什么不干脆全量打包**：全量可变 17.7 MB，静态 600 全字集也有数 MB。这个站的首屏本来就要拉四路接口，
再加 1.1 MB 字体是把「设计上讲究」变成「用起来更慢」，方向反了。
