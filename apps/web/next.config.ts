import type { NextConfig } from 'next'

/**
 * **Node 运行时**（Next standalone），不是静态导出。
 *
 * 这里原来是 `output: 'export'`，理由是「产物由 geo-api 同源托管」——
 * 前后端分离（D1）之后那个理由就没了，而静态导出的代价一直留着：
 * 它要求动态路由段能被 generateStaticParams 预先枚举，
 * 而 task / run / response 的 id 都持续增长。IA 以任务为主干之后，
 * 全站主路径都得退化成查询参数（/task/?id=34&run=128&rid=29）。
 *
 * 换成 Node 运行时得到：
 *   · 真实路由 /tasks/34/runs/128/r/29 —— 运营要把证据链接发给客户
 * （原先这里还列了「服务端能在渲染前拦未登录」—— 那条是错的：
 *   geo_session 是 geo-api.xg22.top 的 host-only Cookie，
 *   geo.xg22.top 上的 Next 服务器同样看不到。鉴权只能在客户端判断。）
 *
 * 代价（尚未实施，见 README §9）：
 *   VPS 上多一个常驻进程，且要改共用的 Caddyfile（同机还有别的项目，
 *   改前备份、只 reload 不 restart）。
 *
 * 开发期取数走下面的 rewrites 代理，浏览器眼里全是同源。
 * 后端 set_cookie 不带 domain（host-only，见 apps/api/app/api/auth.py），
 * 所以 Set-Cookie 会落到 localhost 名下，不会因域名不匹配被丢；
 * Cookie 带的 Secure 在 http://localhost 上浏览器也放行（localhost 算可信来源）。
 * **零后端改动** —— 相对「直连 + 把 localhost 加进 CORS_ALLOW_ORIGINS」的主要优势。
 */
const API_ORIGIN = process.env.API_ORIGIN ?? 'https://geo-api.xg22.top'

// `/qa` 是后端的运维质检页。配置类页面全部进产品前端之后它只剩运维用途，
// 侧栏那个相对链接要拿掉（分离部署下它指向 geo.xg22.top/qa，那里没有 /qa）。
// 代理保留：开发期偶尔要开它对数据。
const PROXY_PREFIXES = ['/v1', '/qa', '/health']

const nextConfig: NextConfig = {
  output: 'standalone',
  async rewrites() {
    // 生产是跨站直连 geo-api.xg22.top（CORS + 跨站 Cookie 已配好），不走代理
    if (process.env.NODE_ENV === 'production') return []
    return PROXY_PREFIXES.map((prefix) => ({
      source: `${prefix}/:path*`,
      destination: `${API_ORIGIN}${prefix}/:path*`,
    }))
  },
}

export default nextConfig
