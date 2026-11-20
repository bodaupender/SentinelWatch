import { Routes, Route, Navigate } from 'react-router-dom'
import { LoginPage } from '@pages/LoginPage'
import { DashboardPage } from '@pages/DashboardPage'
import { AgentsPage } from '@pages/AgentsPage'
import { EndpointManagementPage } from '@pages/EndpointManagementPage'
import { ProcessesPage } from '@pages/ProcessesPage'
import { ProcessExplorerPage } from '@pages/ProcessExplorerPage'
import { ServicesPage } from '@pages/ServicesPage'
import { ServiceInvestigationPage } from '@pages/ServiceInvestigationPage'
import { AlertsPage } from '@pages/AlertsPage'
import { AlertInvestigationPage } from '@pages/AlertInvestigationPage'
import { WindowsEventsPage } from '@pages/WindowsEventsPage'
import { DetectionRulesPage } from '@pages/DetectionRulesPage'
import { ReportsPage } from '@pages/ReportsPage'
import { AuditPage } from '@pages/AuditPage'
import { SettingsPage } from '@pages/SettingsPage'
import { AIInvestigationPage } from '@pages/AIInvestigationPage'
import { EnrollmentTokensPage } from '@pages/EnrollmentTokensPage'
import { useAuthStore } from '@hooks/useAuthStore'
import { Layout } from '@components/layout/Layout'

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useAuthStore()

  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
      </div>
    )
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }

  return <>{children}</>
}

function PublicRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useAuthStore()

  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
      </div>
    )
  }

  if (isAuthenticated) {
    return <Navigate to="/" replace />
  }

  return <>{children}</>
}

export default function App() {
  return (
    <Routes>
      <Route
        path="/login"
        element={
          <PublicRoute>
            <LoginPage />
          </PublicRoute>
        }
      />
      <Route
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route path="/" element={<DashboardPage />} />
        <Route path="/agents" element={<AgentsPage />} />
        <Route path="/endpoints" element={<EndpointManagementPage />} />
        <Route path="/processes" element={<ProcessesPage />} />
        <Route path="/process-explorer" element={<ProcessExplorerPage />} />
        <Route path="/services" element={<ServicesPage />} />
        <Route path="/service/:id" element={<ServiceInvestigationPage />} />
        <Route path="/alerts" element={<AlertsPage />} />
        <Route path="/ai-investigation" element={<AIInvestigationPage />} />
        <Route path="/alert/:id" element={<AlertInvestigationPage />} />
        <Route path="/windows-events" element={<WindowsEventsPage />} />
        <Route path="/rules" element={<DetectionRulesPage />} />
        <Route path="/reports" element={<ReportsPage />} />
        <Route path="/audit" element={<AuditPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/enrollment-tokens" element={<EnrollmentTokensPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
