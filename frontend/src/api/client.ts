/** 统一请求封装（06 §5.1）：统一解包 {code,message,data}。
 *
 * 硬约束：禁止只看 HTTP 200 判定业务成功——业务 code≠0 一律抛 BizError；
 * 网络失败（后端未启动）→ 自动降级到 mock 通道并置降级横幅（FR-5.5，不白屏）。
 */
import { handleMock, USE_MOCK, type MockRequest } from '@/mock'
import { useSystemStore } from '@/stores/useSystemStore'

export class BizError extends Error {
  code: number
  data: any
  constructor(code: number, message: string, data?: any) {
    super(message)
    this.code = code
    this.data = data
  }
}

const BASE: string = import.meta.env.VITE_API_BASE ?? ''

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE'
  query?: Record<string, any>
  body?: any
}

function buildUrl(path: string, query?: Record<string, any>): string {
  const qs = query
    ? '?' + Object.entries(query)
        .filter(([, v]) => v !== undefined && v !== null && v !== '')
        .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
        .join('&')
    : ''
  return `${BASE}/api/v1${path}${qs}`
}

export async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const system = useSystemStore()
  const mockReq: MockRequest = { path, method: opts.method, query: opts.query, body: opts.body }

  if (USE_MOCK) {
    system.mockMode = true
    return handleMock<T>(mockReq)
  }

  try {
    const res = await fetch(buildUrl(path, opts.query), {
      method: opts.method ?? 'GET',
      headers: opts.body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    })
    const payload = await res.json()
    if (payload.code !== 0) {
      // 业务错误码非 0 一律抛错（06 §5.1 硬约束）
      throw new BizError(payload.code, payload.message ?? '业务错误', payload.data)
    }
    system.mockMode = false
    system.degraded = false
    return payload.data as T
  } catch (err) {
    if (err instanceof BizError) throw err
    // 网络失败 → 降级：顶部横幅 + mock 数据，页面不白屏
    system.degraded = true
    system.mockMode = true
    return handleMock<T>(mockReq)
  }
}
