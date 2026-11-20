import { Menu, Bell, Shield, LogOut, User, Settings, Moon, Sun } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import api from '@lib/api'
import { useAuthStore } from '@hooks/useAuthStore'
import { useThemeStore } from '@hooks/useThemeStore'

export function Header() {
  const [showUserMenu, setShowUserMenu] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const navigate = useNavigate()
  const { user, logout } = useAuthStore()
  const { isAuthenticated, selectedOrganizationId, setSelectedOrganizationId } = useAuthStore()
  const queryClient = useQueryClient()
  const { theme, toggleTheme } = useThemeStore()
  const organizationsQuery = useQuery({
    queryKey: ['organizations'],
    queryFn: async () => (await api.get<Array<{ id: string; name: string; role: string }>>('/api/v1/organizations')).data,
    enabled: isAuthenticated,
  })
  const organizations = organizationsQuery.data ?? []
  useEffect(() => {
    const firstOrganization = organizations[0]
    if (firstOrganization && !organizations.some((organization) => organization.id === selectedOrganizationId)) {
      setSelectedOrganizationId(firstOrganization.id)
    }
  }, [organizations, selectedOrganizationId, setSelectedOrganizationId])

  return (
    <header className="flex h-16 items-center gap-4 border-b bg-card px-4 shadow-sm">
      {/* Mobile sidebar toggle */}
      <button
        onClick={() => setSidebarOpen(!sidebarOpen)}
        className="md:hidden inline-flex h-10 w-10 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
        aria-label="Toggle sidebar"
      >
        <Menu className="h-5 w-5" />
      </button>

      {/* Logo/Title */}
      <div className="flex items-center gap-2 md:hidden">
        <Shield className="h-6 w-6 text-primary" />
        <span className="font-semibold text-lg">SentinelWatch</span>
      </div>

      {/* Search (placeholder) */}
      <div className="hidden md:flex md:flex-1 md:max-w-md">
        <div className="relative w-full">
          <input
            type="search"
            placeholder="Search agents, processes, alerts..."
            className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 pl-10"
          />
          <span className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground">
            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
          </span>
        </div>
      </div>

      {/* Desktop logo */}
      <div className="hidden md:flex items-center gap-2">
        <Shield className="h-6 w-6 text-primary" />
        <span className="font-semibold text-lg">SentinelWatch</span>
      </div>

      {/* Right side actions */}
      <div className="flex flex-1 items-center justify-end gap-2">
        {organizations.length > 1 && (
          <label className="sr-only" htmlFor="organization-select">Organization</label>
        )}
        {organizations.length > 1 && (
          <select
            id="organization-select"
            aria-label="Organization"
            value={selectedOrganizationId ?? ''}
            onChange={(event) => {
              setSelectedOrganizationId(event.target.value || null)
              queryClient.removeQueries({ predicate: (query) => query.queryKey[0] !== 'organizations' })
            }}
            className="h-9 max-w-48 rounded-md border border-input bg-background px-2 text-sm"
          >
            {organizations.map((organization) => <option key={organization.id} value={organization.id}>{organization.name}</option>)}
          </select>
        )}
        {/* Notifications */}
        <button className="relative inline-flex h-10 w-10 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground">
          <Bell className="h-5 w-5" />
          <span className="absolute top-1 right-1 h-2 w-2 rounded-full bg-destructive" />
        </button>

        {/* Theme toggle */}
        <button
          onClick={toggleTheme}
          className="inline-flex h-10 w-10 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          aria-label="Toggle theme"
        >
          {theme === 'dark' ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
        </button>

        {/* User menu */}
        <div className="relative">
          <button
            onClick={() => setShowUserMenu(!showUserMenu)}
            className="flex h-10 w-10 items-center justify-center rounded-full bg-primary/10 text-primary transition-colors hover:bg-primary/20"
            aria-label="User menu"
          >
            <User className="h-5 w-5" />
          </button>

          {showUserMenu && (
            <>
              <div
                className="fixed inset-0 z-40"
                onClick={() => setShowUserMenu(false)}
                aria-hidden="true"
              />
              <div className="absolute right-0 mt-2 w-56 origin-top-right rounded-md bg-popover p-1 shadow-lg ring-1 ring-border z-50 animate-fade-in">
                <div className="px-3 py-2 border-b">
                  <p className="text-sm font-medium">{user?.full_name || user?.username}</p>
                  <p className="text-xs text-muted-foreground">{user?.email}</p>
                  <p className="text-xs text-muted-foreground capitalize">{user?.role}</p>
                </div>
                <button
                  onClick={() => { navigate('/settings'); setShowUserMenu(false); }}
                  className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
                >
                  <Settings className="h-4 w-4" />
                  Settings
                </button>
                <button
                  onClick={() => { logout(); setShowUserMenu(false); }}
                  className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm text-destructive transition-colors hover:bg-accent"
                >
                  <LogOut className="h-4 w-4" />
                  Sign out
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </header>
  )
}
