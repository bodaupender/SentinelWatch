import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'

type Theme = 'light' | 'dark' | 'system'

interface ThemeState {
  theme: Theme
  resolvedTheme: 'light' | 'dark'
  setTheme: (theme: Theme) => void
  toggleTheme: () => void
  initializeTheme: () => void
}

export const useThemeStore = create<ThemeState>()(
  persist(
    (set, get) => ({
      theme: 'system',
      resolvedTheme: 'light',

      setTheme: (theme: Theme) => {
        set({ theme })
        get().initializeTheme()
      },

      toggleTheme: () => {
        const { theme } = get()
        const themes: Theme[] = ['light', 'dark', 'system']
        const currentIndex = themes.indexOf(theme)
        const nextTheme = themes[(currentIndex + 1) % themes.length]
        set({ theme: nextTheme })
        get().initializeTheme()
      },

      initializeTheme: () => {
        const { theme } = get()
        let resolved: 'light' | 'dark' = 'light'

        if (theme === 'system') {
          resolved = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
        } else {
          resolved = theme
        }

        set({ resolvedTheme: resolved })
        document.documentElement.classList.toggle('dark', resolved === 'dark')
      },
    }),
    {
      name: 'sentinelwatch-theme',
      storage: createJSONStorage(() => localStorage),
    }
  )
)

// Initialize theme on client side
if (typeof window !== 'undefined') {
  useThemeStore.getState().initializeTheme()

  // Listen for system theme changes
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
    const { theme } = useThemeStore.getState()
    if (theme === 'system') {
      useThemeStore.getState().initializeTheme()
    }
  })
}
