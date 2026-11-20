import axios from 'axios'
import type { AxiosError, InternalAxiosRequestConfig } from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '',
  withCredentials: true,
  headers: { 'Content-Type': 'application/json' },
})

api.interceptors.request.use(async (config) => {
  // Import lazily to avoid an initialization cycle with the auth store.
  const { useAuthStore } = await import('@hooks/useAuthStore')
  const { accessToken, selectedOrganizationId } = useAuthStore.getState()
  if (accessToken) config.headers.Authorization = `Bearer ${accessToken}`
  if (selectedOrganizationId) config.headers['X-Organization-ID'] = selectedOrganizationId
  return config
})

type RetryableRequest = InternalAxiosRequestConfig & { _retry?: boolean }
let refreshInProgress = false
let waitingRequests: Array<{
  resolve: (token: string | null) => void
  reject: (reason: unknown) => void
}> = []

function settleWaitingRequests(error: unknown, token: string | null = null): void {
  for (const waiting of waitingRequests) {
    if (error) waiting.reject(error)
    else waiting.resolve(token)
  }
  waitingRequests = []
}

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const request = error.config as RetryableRequest | undefined
    if (!request || error.response?.status !== 401 || request._retry) throw error

    const url = request.url ?? ''
    if (['/auth/login', '/auth/refresh', '/auth/register', '/auth/logout'].some((path) => url.includes(path))) throw error

    if (refreshInProgress) {
      const token = await new Promise<string | null>((resolve, reject) => {
        waitingRequests.push({ resolve, reject })
      })
      if (token) request.headers.Authorization = `Bearer ${token}`
      return api(request)
    }

    request._retry = true
    refreshInProgress = true
    try {
      const { useAuthStore } = await import('@hooks/useAuthStore')
      await useAuthStore.getState().refreshAccessToken()
      const token = useAuthStore.getState().accessToken
      if (!token) throw new Error('Session refresh failed')
      settleWaitingRequests(null, token)
      if (token) request.headers.Authorization = `Bearer ${token}`
      return api(request)
    } catch (refreshError) {
      settleWaitingRequests(refreshError)
      const { useAuthStore } = await import('@hooks/useAuthStore')
      void useAuthStore.getState().logout()
      if (typeof window !== 'undefined') window.location.assign('/login')
      throw refreshError
    } finally {
      refreshInProgress = false
    }
  },
)

export const authApi = {
  login: (username: string, password: string, mfaCode?: string) => {
    const body = new URLSearchParams({ username, password })
    if (mfaCode) body.set('mfa_code', mfaCode)
    return api.post('/api/v1/auth/login', body, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    })
  },
  register: (payload: { username: string; email: string; full_name?: string; password: string }) =>
    api.post('/api/v1/auth/register', payload),
  updateProfile: (payload: Record<string, unknown>) => api.patch('/api/v1/auth/me', payload),
  mfaSetup: () => api.post('/api/v1/auth/mfa/setup'),
  mfaVerify: (code: string) => api.post('/api/v1/auth/mfa/verify', { code }),
  mfaDisable: (code: string) => api.post('/api/v1/auth/mfa/disable', { code }),
  changePassword: (current_password: string, new_password: string) =>
    api.post('/api/v1/auth/password/change', { current_password, new_password }),
}

export default api
