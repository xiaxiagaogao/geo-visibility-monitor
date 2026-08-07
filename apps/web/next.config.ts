import type { NextConfig } from 'next'

/**
 * 生产：静态导出，产物挂在 https://geo.xg22.top 由 Caddy 托管。
 * 开发：**不能**开 export —— 一开 rewrites 就失效，而开发期取数要靠它。
 *
 * 早先这里写的是「产物由 geo-api 同源托管」，那是前后端分离之前的方案，已作废：
 * 现在 API 在 geo-api.xg22.top、前端在 geo.xg22.top，是两个站点。
 * 静态导出本身保留 —— Caddy 的 file_server 直接 serve out/ 即可。
 *
 * 开发期取数有两条路，接 API 那一轮实测后再定（本轮吃固定数据，两条都没走）：
 *   A. 走下面的 rewrites 代理。浏览器眼里全是 localhost:3000 同源。
 *      后端 set_cookie 不带 domain（host-only，见 apps/api/app/api/auth.py），
 *      所以 Set-Cookie 会落到 localhost 名下，不会因域名不匹配被丢；
 *      Cookie 带的 Secure 在 http://localhost 上浏览器也放行（localhost 算可信来源）。
 *      **零后端改动**，这是它相对 B 的主要优势。
 *   B. 直连 geo-api.xg22.top。要把 http://localhost:3000 加进 VPS 上的
 *      CORS_ALLOW_ORIGINS —— 改 env 得上 VPS。
 */
const isProd = process.env.NODE_ENV === 'production'

const API_ORIGIN = process.env.API_ORIGIN ?? 'https://geo-api.xg22.top'
// `/qa` 是后端的运维质检页，侧栏有个外链指过来。
// ⚠️ 分离部署后这个相对链接在生产是坏的：geo.xg22.top 上只有静态产物，没有 /qa。
//    要么改成绝对地址 https://geo-api.xg22.top/qa，要么从侧栏拿掉。接 API 那一轮一并处理。
const PROXY_PREFIXES = ['/v1', '/qa', '/health']

const nextConfig: NextConfig = {
  output: isProd ? 'export' : undefined,
  // 导出成 out/responses/index.html 而不是 out/responses.html——
  // 静态服务器遇到目录会找 index.html，但不会自动补 .html。
  // （这条最早是为 Starlette StaticFiles 写的，换 Caddy file_server 后行为一致，故保留）
  trailingSlash: true,
  images: { unoptimized: true },
  // 注意：`rewrites` 这个键**存在**就会触发 export 的告警，哪怕函数返回空数组。
  // 所以生产构建时整个键都不能出现。
  ...(isProd
    ? {}
    : {
        async rewrites() {
          return PROXY_PREFIXES.map((prefix) => ({
            source: `${prefix}/:path*`,
            destination: `${API_ORIGIN}${prefix}/:path*`,
          }))
        },
      }),
}

export default nextConfig
