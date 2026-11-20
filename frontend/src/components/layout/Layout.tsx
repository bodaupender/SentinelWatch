import { Outlet } from 'react-router-dom'
import { Header } from './Header'
import { Sidebar } from './Sidebar'
import { LiveUpdatesBridge } from '@components/LiveUpdatesBridge'

export function Layout() {
  return (
    <div className="flex h-screen flex-col overflow-hidden bg-background">
      <LiveUpdatesBridge />
      <Header />
      <div className="flex min-h-0 flex-1">
        <Sidebar />
        <main className="min-w-0 flex-1 overflow-auto p-4 md:p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
