/**
 * Axios instance + interceptors.
 *
 * - Request: attach `Authorization: Bearer <access_token>` when present.
 * - Response: implement sliding token refresh — every authenticated request
 *   may receive a fresh access token in the `X-Access-Token` response header
 *   (set by the backend middleware). We pick it up and persist it.
 * - 401: attempt a single token refresh, then replay the original request.
 *   If refresh fails, clear auth and redirect to /login.
 */
import axios, {
  type AxiosError,
  type AxiosRequestConfig,
  type InternalAxiosRequestConfig,
} from 'axios'
import type { ApiErrorBody } from '@/types'

const TOKEN_KEYS = {
  access: 'ain_access_token',
  refresh: 'ain_refresh_token',
} as const

export const tokenStorage = {
  getAccess: () => localStorage.getItem(TOKEN_KEYS.access),
  getRefresh: () => localStorage.getItem(TOKEN_KEYS.refresh),
  set: (access: string, refresh: string) => {
    localStorage.setItem(TOKEN_KEYS.access, access)
    localStorage.setItem(TOKEN_KEYS.refresh, refresh)
  },
  setAccess: (access: string) => localStorage.setItem(TOKEN_KEYS.access, access),
  clear: () => {
    localStorage.removeItem(TOKEN_KEYS.access)
    localStorage.removeItem(TOKEN_KEYS.refresh)
  },
}

export const http = axios.create({
  baseURL: '/api',
  timeout: 20000,
})

http.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = tokenStorage.getAccess()
  if (token) {
    config.headers = config.headers ?? {}
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

http.interceptors.response.use(
  (response) => {
    // Sliding refresh — pick up a rotated access token if the backend sent one.
    const newToken = response.headers['x-access-token']
    if (typeof newToken === 'string' && newToken) {
      tokenStorage.setAccess(newToken)
    }
    return response
  },
  async (error: AxiosError<ApiErrorBody>) => {
    const original = error.config as InternalAxiosRequestConfig & {
      _retried?: boolean
    }

    // Only attempt refresh once, and only for token-expiry 401s (not login
    // endpoints, which also 401 on bad credentials).
    const status = error.response?.status
    const url = original?.url ?? ''
    const isAuthEndpoint = url.includes('/v1/auth/login') || url.includes('/v1/auth/register')

    if (status === 401 && original && !original._retried && !isAuthEndpoint) {
      original._retried = true
      const refresh = tokenStorage.getRefresh()
      if (refresh) {
        try {
          const { data } = await axios.post('/api/v1/auth/refresh', {
            refresh_token: refresh,
          })
          tokenStorage.set(data.access_token, data.refresh_token)
          // Replay the original request with the new token.
          original.headers = original.headers ?? {}
          original.headers.Authorization = `Bearer ${data.access_token}`
          return http(original)
        } catch {
          // fall through to logout
        }
      }
      tokenStorage.clear()
      // Avoid hard import cycle with router; dispatch a redirect event.
      window.dispatchEvent(new CustomEvent('auth:logout'))
      return Promise.reject(error)
    }

    return Promise.reject(error)
  },
)

/** Convenience helper for typed GETs returning the data directly. */
export async function apiGet<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
  const { data } = await http.get<T>(url, config)
  return data
}

/** Convenience helper for typed POSTs returning the data directly. */
export async function apiPost<T>(url: string, body?: unknown, config?: AxiosRequestConfig): Promise<T> {
  const { data } = await http.post<T>(url, body, config)
  return data
}

/** Extract a human-readable message from any axios error. */
export function extractErrorMessage(err: unknown, fallback = '请求失败'): string {
  if (axios.isAxiosError(err)) {
    const body = err.response?.data as ApiErrorBody | undefined
    if (typeof body?.detail === 'string' && body.detail) return body.detail
    if (err.message) return err.message
  }
  if (err instanceof Error) return err.message
  return fallback
}
