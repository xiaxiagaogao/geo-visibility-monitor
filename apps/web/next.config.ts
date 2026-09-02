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
 *   · 服务端能在渲染前拦未登录 —— 2026-08-11 合并成同源之后这条**成立了**：
 *     Cookie 与前端同域，Next 服务器看得见。（分成两个域名的那段时间里
 *     它是不成立的，我一度把它当理由写在这儿，后来撤回过。）
 *
 * 代价（尚未实施，见 README §9）：
 *   VPS 上多一个常驻进程，且要改共用的 Caddyfile（同机还有别的项目，
 *   改前备份、只 reload 不 restart）。
 *
 * 开发期仍走下面的 rewrites 代理：本机 localhost:3000 与线上 geo.example.com
 * 不是同一个 Origin，代理让浏览器眼里全是同源，和生产行为一致。
 * 后端 set_cookie 不带 domain（host-only），Set-Cookie 会落到 localhost 名下；
 * Cookie 带的 Secure 在 http://localhost 上浏览器也放行（localhost 算可信来源）。
 */
/**
 * 开发期 `/v1` 代理到哪。
 *
 * **默认值是占位符，本机开发必须自己设** —— 在 `apps/web/.env.local` 里写
 * `API_ORIGIN=https://你的部署域名`（`.env.local` 被 gitignore，不会进仓库）。
 * 仓库里不放真实域名：这是个公开仓库，而它把鉴权模型、接口面、部署架构
 * 都写清楚了，再配上真实地址等于把攻击面一并发出去。
 */
const API_ORIGIN = process.env.API_ORIGIN ?? 'https://geo.example.com'

// `/qa` 是后端的运维质检页。同源之后它就在 geo.example.com/qa 下，
// 侧栏那个相对链接**是通的**（分离部署那段时间里它是坏的，已不再是问题）。
// 等配置类页面（A2-A4）做完，/qa 只剩运维用途，届时再决定要不要从侧栏拿掉。
const PROXY_PREFIXES = ['/v1', '/qa', '/health']

const nextConfig: NextConfig = {
  output: 'standalone',
  async rewrites() {
    // 生产同源（Caddy 按路径分流），不需要代理
    if (process.env.NODE_ENV === 'production') return []
    return PROXY_PREFIXES.map((prefix) => ({
      source: `${prefix}/:path*`,
      destination: `${API_ORIGIN}${prefix}/:path*`,
    }))
  },
}

export default nextConfig
