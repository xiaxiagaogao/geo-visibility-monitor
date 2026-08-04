import type { NextConfig } from 'next'

/**
 * 生产：静态导出，产物由 geo-api 同源托管（docs/27 §4 决定 ①②）。
 * 开发：**不能**开 export —— 一开 rewrites 就失效，而开发期取数全靠它。
 *
 * 为什么开发期非要代理：Cookie `geo_qa_key` 是 HttpOnly + SameSite=lax，
 * 前端直连 96.9.213.230:8200 属跨源，API 又没开 CORS。走 rewrites 之后
 * 浏览器眼里全部是 localhost:3000 同源，登录 / 读接口 / <img> 拉截图一次性都通。
 */
const isProd = process.env.NODE_ENV === 'production'

const API_ORIGIN = process.env.API_ORIGIN ?? 'http://96.9.213.230:8200'
const PROXY_PREFIXES = ['/v1', '/qa', '/health']

const nextConfig: NextConfig = {
  output: isProd ? 'export' : undefined,
  // 导出成 out/responses/index.html 而不是 out/responses.html——
  // Starlette 的 StaticFiles 遇到目录会找 index.html，但不会自动补 .html
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
