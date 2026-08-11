/**
 * 请求层 —— 所有取数的唯一出口。
 *
 * 这一层只管「把请求发对、把错误分对类」，**不碰 React、不算比率、不做跳转**。
 * 跳转要 router，放这里就没法脱离浏览器测；比率是 `lib/l3` 的事。
 *
 * 同源部署（Caddy 按路径分流），所以路径直接写 `/v1/...`，不需要 base URL。
 * 开发期由 next.config.ts 的 rewrites 代理到线上，浏览器眼里同样是同源。
 */

/** 服务端返回的非 2xx。**保留 status，调用方据此分流。** */
export class ApiError extends Error {
  readonly status: number
  readonly detail: string

  constructor(status: number, detail: string) {
    super(`HTTP ${status}: ${detail}`)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

/**
 * CSRF token 存**模块级变量**，不进 localStorage（XSS 偷不走），
 * 也不放 React context —— 放了这个文件就得依赖 React，没法单独测。
 *
 * 由 AuthProvider 在 login / me 之后调 `setCsrfToken` 灌进来。
 */
let csrfToken: string | null = null

export function setCsrfToken(token: string | null): void {
  csrfToken = token
}

/** 需要 CSRF 头的方法。GET/HEAD/OPTIONS 是安全方法，后端也不校验。 */
const WRITE_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE'])

export interface ApiInit {
  method?: string
  /** 对象会被 JSON 序列化并自动带上 Content-Type */
  body?: unknown
  /** `undefined` / `null` 的键会被丢掉，避免发出 `?platform=undefined` */
  query?: Record<string, string | number | boolean | null | undefined>
  signal?: AbortSignal
}

function buildUrl(path: string, query?: ApiInit['query']): string {
  if (!query) return path
  const params = new URLSearchParams()
  for (const [k, v] of Object.entries(query)) {
    // 只丢 undefined 与 null —— false 和 0 是有意义的值，不能被真值判断吃掉
    if (v === undefined || v === null) continue
    params.append(k, String(v))
  }
  const qs = params.toString()
  return qs ? `${path}?${qs}` : path
}

/** FastAPI 校验错误的一条：`{ loc, msg, type }` */
interface ValidationIssue {
  msg?: unknown
}

async function readDetail(res: Response): Promise<string> {
  // 网关的 502/503 是纯文本，硬解 JSON 会抛在解析处，
  // 把真正的失败原因（网关挂了）盖掉。
  try {
    const ct = res.headers.get('content-type') ?? ''
    if (ct.includes('application/json')) {
      const body = (await res.json()) as { detail?: unknown }
      const detail = body?.detail

      // 业务错误：detail 是一句话
      if (typeof detail === 'string') return detail

      // 校验错误（422）：detail 是 [{ loc, msg, type }]。
      // 不处理的话会掉到下面的 statusText，用户看到一句英文
      // "Unprocessable Entity" —— 等于没说。
      if (Array.isArray(detail)) {
        const msgs = detail
          .map((d) => (d as ValidationIssue)?.msg)
          .filter((m): m is string => typeof m === 'string')
        if (msgs.length) return msgs.join('；')
      }
    }
  } catch {
    /* 落到下面的兜底 */
  }
  return res.statusText || `请求失败（${res.status}）`
}

/**
 * 发一个请求。非 2xx 一律抛 `ApiError`。
 *
 * **不在这里处理 401 跳登录。** 那是调用方（AuthProvider）的事：
 * 这一层做跳转就需要 router，测起来要拖进整个 React 树。
 */
export async function apiFetch<T = unknown>(path: string, init: ApiInit = {}): Promise<T> {
  const method = (init.method ?? 'GET').toUpperCase()
  const headers: Record<string, string> = {}

  if (init.body !== undefined) headers['Content-Type'] = 'application/json'

  // 写操作**无条件**带上，不给「先不带以后再加」留口子。
  // token 为空时照发不误，让后端的 403 说话 —— 前端自己拦会把
  // 「后端到底开没开 CSRF」这件事藏起来。
  if (WRITE_METHODS.has(method) && csrfToken) headers['X-CSRF-Token'] = csrfToken

  const res = await fetch(buildUrl(path, init.query), {
    method,
    headers,
    // 跨站时不带就没有身份；同源下是默认行为，写明让意图清楚
    credentials: 'include',
    body: init.body === undefined ? undefined : JSON.stringify(init.body),
    signal: init.signal,
  })

  if (!res.ok) throw new ApiError(res.status, await readDetail(res))

  // 204 没有 body（logout 就是），硬解会抛
  if (res.status === 204) return null as T
  return (await res.json()) as T
}
