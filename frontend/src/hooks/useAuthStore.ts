import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'
import api, { authApi } from '@lib/api'

interface User {
  id: string
  username: string
  email: string
  full_name?: string
  role: 'admin' | 'analyst' | 'viewer' | 'agent'
  mfa_enabled: boolean
}

interface AuthState {
  user: User | null
  accessToken: string | null
  refreshToken: string | null
  isAuthenticated: boolean
  isLoading: boolean
  selectedOrganizationId: string | null
  login: (username: string, password: string, mfaCode?: string) => Promise<void>
  logout: () => Promise<void>
  refreshAccessToken: () => Promise<void>
  checkAuth: () => Promise<void>
  setTokens: (access: string, refresh: string) => void
  setSelectedOrganizationId: (organizationId: string | null) => void
}

type PersistedAuthState = Pick<AuthState, 'user' | 'accessToken' | 'refreshToken' | 'isAuthenticated'>

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,
      isLoading: true,
      selectedOrganizationId: typeof window === 'undefined' ? null : window.localStorage.getItem('sentinelwatch-organization'),

      setSelectedOrganizationId: (organizationId) => {
        if (organizationId) window.localStorage.setItem('sentinelwatch-organization', organizationId)
        else window.localStorage.removeItem('sentinelwatch-organization')
        set({ selectedOrganizationId: organizationId })
      },

      setTokens: (access: string, refresh: string) => {
        set({ accessToken: access, refreshToken: refresh })
      },

      login: async (username: string, password: string, mfaCode?: string) => {
        set({ isLoading: true })
        try {
          const response = await authApi.login(username, password, mfaCode)
          const { access_token, refresh_token } = response.data
          const userResponse = await api.get('/api/v1/auth/me', {
            headers: { Authorization: `Bearer ${access_token}` },
          })

          set({
            user: userResponse.data,
            accessToken: access_token,
            refreshToken: refresh_token,
            isAuthenticated: true,
            isLoading: false,
          })

          // Store tokens in httpOnly cookies via backend
          // The backend sets cookies, we just keep tokens in memory for API calls
        } catch (error) {
          set({ isLoading: false })
          throw error
        }
      },

      logout: async () => {
        const { refreshToken } = get()
        try {
          await api.post('/api/v1/auth/logout', refreshToken ? { refresh_token: refreshToken } : undefined)
        } catch {
          // Ignore logout errors
        } finally {
          set({
            user: null,
            accessToken: null,
            refreshToken: null,
            isAuthenticated: false,
            selectedOrganizationId: null,
          })
          if (typeof window !== 'undefined') window.localStorage.removeItem('sentinelwatch-organization')
        }
      },

      refreshAccessToken: async () => {
        const { refreshToken } = get()
        try {
          const response = await api.post(
            '/api/v1/auth/refresh',
            refreshToken ? { refresh_token: refreshToken } : undefined,
          )

          const { access_token, refresh_token } = response.data
          set({ accessToken: access_token, refreshToken: refresh_token })
        } catch (error) {
          set({
            user: null,
            accessToken: null,
            refreshToken: null,
            isAuthenticated: false,
          })
          throw error
        }
      },

      checkAuth: async () => {
        try {
          if (!get().accessToken) await get().refreshAccessToken()
          if (!get().accessToken) throw new Error('Session expired')
          const response = await api.get('/api/v1/auth/me')
          set({ user: response.data, isAuthenticated: true })
        } catch {
          set({
            user: null,
            accessToken: null,
            refreshToken: null,
            isAuthenticated: false,
          })
        } finally {
          set({ isLoading: false })
        }
      },
    }),
    {
      name: 'sentinelwatch-auth',
      storage: createJSONStorage<PersistedAuthState>(() => {
        // In-memory only: tokens are also held by the backend in HttpOnly
        // cookies, so we never persist secrets to localStorage.
        const store: Record<string, string> = {}
        return {
          getItem: (key: string): string | null =>
            Object.prototype.hasOwnProperty.call(store, key) ? store[key] ?? null : null,
          setItem: (key: string, value: string): void => {
            store[key] = value
          },
          removeItem: (key: string): void => {
            delete store[key]
          },
        }
      }),
      partialize: (state): PersistedAuthState => ({
        user: state.user,
        accessToken: state.accessToken,
        refreshToken: state.refreshToken,
        isAuthenticated: state.isAuthenticated,
      }),
    }
  )
)

// Initialize auth on app load
if (typeof window !== 'undefined') {
  useAuthStore.getState().checkAuth()
}
