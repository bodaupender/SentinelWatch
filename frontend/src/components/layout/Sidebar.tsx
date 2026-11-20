import { NavLink, useLocation } from 'react-router-dom'
import {
  LayoutDashboard,
  Server,
  Cpu,
  ServerCog,
  AlertTriangle,
  FileCode,
  FileText,
  Settings,
  ChevronLeft,
  ChevronRight,
  Shield,
  Search,
  Activity,
  Network,
  BarChart,
  Bot,
} from 'lucide-react'
import { useState } from 'react'
import { cn } from '@lib/utils'

const navigation = [
  { name: 'Dashboard', href: '/', icon: LayoutDashboard },
  { name: 'Endpoints', href: '/endpoints', icon: Server },
  { name: 'Agents', href: '/agents', icon: Activity },
  { name: 'Processes', href: '/processes', icon: Cpu },
  { name: 'Process Explorer', href: '/process-explorer', icon: Search },
  { name: 'Services', href: '/services', icon: ServerCog },
  { name: 'Alerts', href: '/alerts', icon: AlertTriangle },
  { name: 'AI Investigation', href: '/ai-investigation', icon: Bot },
  { name: 'Windows Events', href: '/windows-events', icon: Network },
  { name: 'Detection Rules', href: '/rules', icon: FileCode },
  { name: 'Reports', href: '/reports', icon: BarChart },
  { name: 'Audit', href: '/audit', icon: FileText },
  { name: 'Settings', href: '/settings', icon: Settings },
] as const

export function Sidebar() {
  const [collapsed, setCollapsed] = useState(false)
  const location = useLocation()

  return (
    <aside
      className={cn(
        'flex h-full shrink-0 flex-col border-r bg-card transition-all duration-200',
        collapsed ? 'w-16' : 'w-64'
      )}
      aria-label="Main navigation"
    >
      {/* Logo */}
      <div className={cn('flex h-16 items-center justify-center gap-2 border-b px-4', collapsed && 'justify-center')}>
        <Shield className="h-6 w-6 text-primary flex-shrink-0" />
        {!collapsed && (
          <span className="font-semibold text-lg truncate">SentinelWatch</span>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto p-4 space-y-1" aria-label="Navigation">
        {navigation.map((item) => {
          const isActive = location.pathname === item.href
          return (
            <NavLink
              key={item.name}
              to={item.href}
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
                  isActive
                    ? 'bg-primary/10 text-primary'
                    : 'text-muted-foreground hover:bg-accent hover:text-foreground',
                  collapsed && 'justify-center px-2'
                )
              }
              title={collapsed ? item.name : undefined}
              aria-current={isActive ? 'page' : undefined}
            >
              <item.icon className="h-5 w-5 flex-shrink-0" aria-hidden="true" />
              {!collapsed && <span className="truncate">{item.name}</span>}
            </NavLink>
          )
        })}
      </nav>

      {/* Collapse toggle */}
      <div className="border-t p-4">
        <button
          onClick={() => setCollapsed(!collapsed)}
          className={cn(
            'flex w-full items-center justify-center gap-2 rounded-md px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-foreground',
            collapsed && 'justify-center'
          )}
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          aria-expanded={!collapsed}
        >
          {collapsed ? (
            <ChevronRight className="h-5 w-5 flex-shrink-0" />
          ) : (
            <>
              <ChevronLeft className="h-5 w-5 flex-shrink-0" />
              <span>Collapse</span>
            </>
          )}
        </button>
      </div>
    </aside>
  )
}
