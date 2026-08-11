/**
 * 请求层 —— 纯逻辑，不依赖 React 与浏览器。
 *
 * 这一层守三件事，每一件出错的方式都是「安静地错」：
 *   · 写操作忘带 CSRF 头 —— 现在开关是关的，不报错；开关一开全线 403
 *   · 401 与 403 混为一谈 —— 403 跳登录会陷入死循环
 *   · 忘带 credentials —— 请求发得出去，但服务端不认识你
 */
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ApiError, apiFetch, setCsrfToken } from './client'

function mockFetch(status: number, body: unknown = {}, contentType = 'application/json') {
  const fn = vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers(contentType ? { 'content-type': contentType } : {}),
    json: async () => body,
    text: async () => JSON.stringify(body),
  })
  globalThis.fetch = fn as unknown as typeof fetch
  return fn
}

/** 断言抛的是 ApiError 并把类型收窄 —— 直接 `.catch(e => e)` 拿到的是 unknown。 */
async function expectApiError(p: Promise<unknown>): Promise<ApiError> {
  const err = await p.then(
    () => null,
    (e: unknown) => e,
  )
  expect(err).toBeInstanceOf(ApiError)
  return err as ApiError
}

afterEach(() => {
  setCsrfToken(null)
  vi.restoreAllMocks()
})

describe('凭证', () => {
  it('每个请求都带 credentials: include', async () => {
    const f = mockFetch(200, { ok: true })
    await apiFetch('/v1/auth/me')
    expect(f.mock.calls[0][1].credentials).toBe('include')
  })
})

describe('CSRF 头', () => {
  it('写方法带上 X-CSRF-Token', async () => {
    setCsrfToken('tok-123')
    const f = mockFetch(200)
    await apiFetch('/v1/tasks', { method: 'POST', body: { name: 'x' } })
    expect(f.mock.calls[0][1].headers['X-CSRF-Token']).toBe('tok-123')
  })

  it.each(['PATCH', 'PUT', 'DELETE'])('%s 也算写方法', async (method) => {
    setCsrfToken('tok-123')
    const f = mockFetch(200)
    await apiFetch('/v1/tasks/1', { method })
    expect(f.mock.calls[0][1].headers['X-CSRF-Token']).toBe('tok-123')
  })

  it('GET 不带这个头 —— 带了无害，但没必要', async () => {
    setCsrfToken('tok-123')
    const f = mockFetch(200)
    await apiFetch('/v1/tasks')
    expect(f.mock.calls[0][1].headers['X-CSRF-Token']).toBeUndefined()
  })

  it('还没登录（token 为 null）时写操作照发，让后端去拒', async () => {
    // 前端不自己拦：拦了会把「后端开没开 CSRF」这件事藏起来，
    // 真正的判定必须来自服务端的 403。
    const f = mockFetch(403, { detail: 'csrf token missing' })
    await expect(apiFetch('/v1/tasks', { method: 'POST' })).rejects.toBeInstanceOf(ApiError)
    expect(f.mock.calls[0][1].headers['X-CSRF-Token']).toBeUndefined()
  })
})

describe('错误分流', () => {
  it('401 抛 ApiError 且 status 是 401', async () => {
    mockFetch(401, { detail: 'not logged in' })
    const err = await expectApiError(apiFetch('/v1/auth/me'))
    expect(err.status).toBe(401)
  })

  it('403 的 status 是 403，不能被当成 401', async () => {
    // 这条是这个文件里最重要的一条：把 403 当 401 处理会跳登录，
    // 而用户本来就登录着 —— 登录成功后又被跳回来，死循环。
    mockFetch(403, { detail: 'requires operator role' })
    const err = await expectApiError(apiFetch('/v1/users'))
    expect(err.status).toBe(403)
    expect(err.status).not.toBe(401)
  })

  it('404 保留 status，调用方自己决定怎么显示', async () => {
    // 后端对「不存在」和「不属于你」都返回 404（防枚举），
    // 前端也就只能当「没有这条」处理，不要试图区分。
    mockFetch(404, { detail: 'task not found' })
    const err = await expectApiError(apiFetch('/v1/tasks/999'))
    expect(err.status).toBe(404)
  })

  it('把后端的 detail 带进错误消息', async () => {
    mockFetch(400, { detail: "platform 'doubao' 尚未接入" })
    const err = await expectApiError(apiFetch('/v1/tasks', { method: 'POST' }))
    expect(err.detail).toContain('doubao')
  })

  it('422 的 detail 是数组（Pydantic 校验错误），要能读出来', async () => {
    // FastAPI 的校验错误形状和业务错误不一样：401 的 detail 是字符串，
    // 422 是 [{ msg, loc, ... }]。只认字符串的话会退回 statusText，
    // 用户看到的是一句英文 "Unprocessable Entity" —— 等于没说。
    mockFetch(422, {
      detail: [
        { type: 'value_error', loc: ['body', 'email'], msg: 'value is not a valid email address' },
      ],
    })
    const err = await expectApiError(apiFetch('/v1/auth/login', { method: 'POST' }))
    expect(err.status).toBe(422)
    expect(err.detail).toContain('valid email address')
  })

  it('422 有多条时都带上', async () => {
    mockFetch(422, {
      detail: [
        { loc: ['body', 'email'], msg: '邮箱格式不对' },
        { loc: ['body', 'samples'], msg: '必须在 1 到 20 之间' },
      ],
    })
    const err = await expectApiError(apiFetch('/v1/tasks', { method: 'POST' }))
    expect(err.detail).toContain('邮箱格式不对')
    expect(err.detail).toContain('必须在 1 到 20 之间')
  })

  it('非 JSON 的错误响应不炸，退回状态码文案', async () => {
    // Caddy 的 502/503 是纯文本，按 JSON 解析会抛在解析处，
    // 把真正的失败原因（网关挂了）盖掉。
    mockFetch(503, 'upstream down', 'text/plain')
    const err = await expectApiError(apiFetch('/v1/tasks'))
    expect(err.status).toBe(503)
  })
})

describe('响应解析', () => {
  it('204 不解析 body', async () => {
    // logout 返回 204，硬解 JSON 会抛。
    const fn = vi.fn().mockResolvedValue({
      ok: true,
      status: 204,
      headers: new Headers(),
      json: async () => {
        throw new Error('不该被调用')
      },
    })
    globalThis.fetch = fn as unknown as typeof fetch
    await expect(apiFetch('/v1/auth/logout', { method: 'POST' })).resolves.toBeNull()
  })

  it('body 是对象时自动 JSON 序列化并带 Content-Type', async () => {
    const f = mockFetch(201)
    await apiFetch('/v1/tasks', { method: 'POST', body: { name: 'x', samples: 3 } })
    expect(f.mock.calls[0][1].headers['Content-Type']).toBe('application/json')
    expect(JSON.parse(f.mock.calls[0][1].body)).toEqual({ name: 'x', samples: 3 })
  })
})

describe('查询参数', () => {
  it('undefined 与 null 的参数不进 URL', async () => {
    // 否则会发出 ?platform=undefined，后端把它当成字符串 "undefined" 去匹配。
    const f = mockFetch(200)
    await apiFetch('/v1/counts', { query: { brand_id: 34, platform: undefined, run_id: null } })
    expect(f.mock.calls[0][0]).toBe('/v1/counts?brand_id=34')
  })

  it('false 与 0 要保留 —— 它们是有意义的值', async () => {
    const f = mockFetch(200)
    await apiFetch('/v1/counts', { query: { include_fake: false, offset: 0 } })
    expect(f.mock.calls[0][0]).toBe('/v1/counts?include_fake=false&offset=0')
  })
})
