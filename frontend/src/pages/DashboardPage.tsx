import { useState } from 'react'
import { Server, AlertTriangle, TrendingUp, Cpu, ServerCog } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from '@components/ui/card'
import { Skeleton } from '@components/ui/skeleton'
import api from '@lib/api'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  LineChart,
  Line,
  PieChart,
  Pie,
  Cell,
} from 'recharts'

interface AlertStatsResponse {
  total: number
  by_severity: Record<string, number>
  by_status: Record<string, number>
}

interface CurrentInventoryResponse {
  data: unknown[]
  total: number
  snapshot_at?: string | null
  is_stale?: boolean
  reporting_agents?: number
  stale_agents?: number
}

interface EndpointReportResponse {
  total_endpoints: number
  enrolled_endpoints?: number
  by_status: Record<string, number>
  by_os: Record<string, number>
  by_version: Record<string, number>
  alerts_per_endpoint: Record<string, number>
}

const SEVERITY_COLORS = {
  critical: '#ef4444',
  high: '#f97316',
  medium: '#eab308',
  low: '#3b82f6',
  info: '#6b7280',
}

const STATUS_COLORS = {
  online: '#22c55e',
  offline: '#6b7280',
  stale: '#eab308',
  unregistered: '#ef4444',
}

export function DashboardPage() {
  const [timeRange, setTimeRange] = useState<'24h' | '7d' | '30d'>('24h')

  const { data: alertStats, isLoading: alertStatsLoading } = useQuery<AlertStatsResponse>({
    queryKey: ['alerts', 'stats', 'summary', timeRange],
    queryFn: async () => {
      const params = new URLSearchParams()
      const now = new Date()
      const end = now.toISOString()
      let start: string
      switch (timeRange) {
        case '24h':
          start = new Date(now.getTime() - 24 * 60 * 60 * 1000).toISOString()
          break
        case '7d':
          start = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000).toISOString()
          break
        case '30d':
          start = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000).toISOString()
          break
      }
      params.set('start_time', start)
      params.set('end_time', end)
      const response = await api.get(`/api/v1/alerts/stats/summary?${params.toString()}`)
      return response.data
    },
    refetchInterval: 60_000,
  })

  const { data: processInventory, isLoading: processesLoading } = useQuery<CurrentInventoryResponse>({
    queryKey: ['telemetry', 'processes', 'current'],
    queryFn: async () => (await api.get('/api/v1/telemetry/processes?limit=1')).data,
    refetchInterval: 15_000,
  })

  const { data: serviceInventory, isLoading: servicesLoading } = useQuery<CurrentInventoryResponse>({
    queryKey: ['telemetry', 'services', 'current'],
    queryFn: async () => (await api.get('/api/v1/telemetry/services?status=running&limit=1')).data,
    refetchInterval: 15_000,
  })

  const { data: endpointReport, isLoading: endpointReportLoading } = useQuery<EndpointReportResponse>({
    queryKey: ['reports', 'endpoints'],
    queryFn: async () => {
      const response = await api.get('/api/v1/reports/endpoints')
      return response.data
    },
    refetchInterval: 60_000,
  })

  const { data: alertReport, isLoading: alertReportLoading } = useQuery({
    queryKey: ['reports', 'alerts', timeRange],
    queryFn: async () => {
      const params = new URLSearchParams()
      const now = new Date()
      const end = now.toISOString()
      let start: string
      switch (timeRange) {
        case '24h':
          start = new Date(now.getTime() - 24 * 60 * 60 * 1000).toISOString()
          break
        case '7d':
          start = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000).toISOString()
          break
        case '30d':
          start = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000).toISOString()
          break
      }
      params.set('start_time', start)
      params.set('end_time', end)
      const response = await api.get(`/api/v1/reports/alerts?${params.toString()}`)
      return response.data
    },
    refetchInterval: 60_000,
  })

  const { data: rulesData, isLoading: rulesLoading } = useQuery<{ total: number; active: number }>({
    queryKey: ['rules', 'count'],
    queryFn: async () => {
      const [customRules, builtinRules] = await Promise.all([
        api.get<Array<{ status: string }>>('/api/v1/rules', { params: { status_filter: 'active', limit: 1000 } }),
        api.get<Array<{ enabled: boolean }>>('/api/v1/rules/builtin'),
      ])
      const total = customRules.data.length + builtinRules.data.filter((rule) => rule.enabled).length
      return { total, active: total }
    },
    refetchInterval: 60_000,
  })

  const stats = [
    {
      name: 'Enrolled Endpoints',
      value: endpointReport?.enrolled_endpoints ?? endpointReport?.total_endpoints ?? 0,
      change: '',
      icon: Server,
      color: 'text-blue-500',
    },
    {
      name: 'Online Endpoints',
      value: endpointReport?.by_status?.online ?? 0,
      change: '',
      icon: ServerCog,
      color: 'text-green-500',
    },
    {
      name: 'Running Processes',
      value: processInventory?.is_stale || !processInventory?.snapshot_at ? '—' : processInventory.total,
      change: processInventory?.is_stale || !processInventory?.snapshot_at
        ? `No fresh snapshot${processInventory?.stale_agents ? ` · ${processInventory.stale_agents} stale` : ''}`
        : `${processInventory.reporting_agents ?? 0} reporting · ${new Date(processInventory.snapshot_at).toLocaleTimeString()}`,
      icon: Cpu,
      color: 'text-blue-500',
    },
    {
      name: 'Running Services',
      value: serviceInventory?.is_stale || !serviceInventory?.snapshot_at ? '—' : serviceInventory.total,
      change: serviceInventory?.is_stale || !serviceInventory?.snapshot_at
        ? `No fresh snapshot${serviceInventory?.stale_agents ? ` · ${serviceInventory.stale_agents} stale` : ''}`
        : `${serviceInventory.reporting_agents ?? 0} reporting · ${new Date(serviceInventory.snapshot_at).toLocaleTimeString()}`,
      icon: ServerCog,
      color: 'text-cyan-500',
    },
    {
      name: 'Active Alerts',
      value: (alertStats?.by_status?.investigating ?? 0) + (alertStats?.by_status?.new ?? 0),
      change: '',
      icon: AlertTriangle,
      color: 'text-red-500',
    },
    {
      name: 'Rules Active',
      value: rulesData?.active ?? 0,
      change: rulesData ? 'active detection rules' : 'No rules loaded',
      icon: TrendingUp,
      color: 'text-purple-500',
    },
  ]

  const severityData = [
    { name: 'Critical', value: alertStats?.by_severity?.critical ?? 0, color: SEVERITY_COLORS.critical },
    { name: 'High', value: alertStats?.by_severity?.high ?? 0, color: SEVERITY_COLORS.high },
    { name: 'Medium', value: alertStats?.by_severity?.medium ?? 0, color: SEVERITY_COLORS.medium },
    { name: 'Low', value: alertStats?.by_severity?.low ?? 0, color: SEVERITY_COLORS.low },
    { name: 'Info', value: alertStats?.by_severity?.info ?? 0, color: SEVERITY_COLORS.info },
  ].filter(d => d.value > 0)

  const statusData = [
    { name: 'Online', value: endpointReport?.by_status?.online ?? 0, color: STATUS_COLORS.online },
    { name: 'Offline', value: endpointReport?.by_status?.offline ?? 0, color: STATUS_COLORS.offline },
    { name: 'Stale', value: endpointReport?.by_status?.stale ?? 0, color: STATUS_COLORS.stale },
    { name: 'Unregistered', value: endpointReport?.by_status?.unregistered ?? 0, color: STATUS_COLORS.unregistered },
  ].filter(d => d.value > 0)

  const timelineData = alertReport?.timeline?.map((t: any) => ({
    time: new Date(t.hour).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' }),
    alerts: t.count,
  })) ?? []

  const osData = Object.entries(endpointReport?.by_os ?? {}).map(([os, count]) => ({ os, count }))

  if (alertStatsLoading || endpointReportLoading || alertReportLoading || processesLoading || servicesLoading || rulesLoading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">Dashboard</h1>
            <p className="text-muted-foreground">Overview of your SentinelWatch deployment</p>
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
          {stats.map((stat) => (
            <Card key={stat.name}>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">{stat.name}</CardTitle>
                <stat.icon className={`h-4 w-4 ${stat.color}`} />
              </CardHeader>
              <CardContent>
                <Skeleton className="h-8 w-24" />
                <Skeleton className="h-4 w-32 mt-2" />
              </CardContent>
            </Card>
          ))}
        </div>

        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-7">
          <Card className="col-span-4">
            <CardHeader>
              <CardTitle>Alert Timeline</CardTitle>
            </CardHeader>
            <CardContent>
              <Skeleton className="h-64 w-full" />
            </CardContent>
          </Card>
          <Card className="col-span-3">
            <CardHeader>
              <CardTitle>Endpoint Health</CardTitle>
            </CardHeader>
            <CardContent>
              <Skeleton className="h-64 w-full" />
            </CardContent>
          </Card>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Dashboard</h1>
          <p className="text-muted-foreground">Overview of your SentinelWatch deployment</p>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={timeRange}
            onChange={(e) => setTimeRange(e.target.value as typeof timeRange)}
            className="flex h-10 w-40 items-center rounded-md border border-input bg-background px-3 py-2 text-sm"
          >
            <option value="24h">Last 24 Hours</option>
            <option value="7d">Last 7 Days</option>
            <option value="30d">Last 30 Days</option>
          </select>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
        {stats.map((stat) => (
          <Card key={stat.name}>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">{stat.name}</CardTitle>
              <stat.icon className={`h-4 w-4 ${stat.color}`} />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stat.value.toLocaleString()}</div>
              {stat.change && <p className="text-xs text-muted-foreground">{stat.change}</p>}
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-7">
        <Card className="col-span-4 lg:col-span-5">
          <CardHeader>
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
              <CardTitle>Alert Timeline</CardTitle>
            </div>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={timelineData}>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                <XAxis dataKey="time" stroke="hsl(var(--muted-foreground))" fontSize={12} />
                <YAxis stroke="hsl(var(--muted-foreground))" fontSize={12} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: 'hsl(var(--popover))',
                    border: '1px solid hsl(var(--border))',
                    borderRadius: '8px',
                  }}
                />
                <Line
                  type="monotone"
                  dataKey="alerts"
                  stroke="hsl(var(--primary))"
                  strokeWidth={2}
                  dot={false}
                  activeDot={{ r: 6 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        <Card className="col-span-3 lg:col-span-2">
          <CardHeader>
            <CardTitle>Alerts by Severity</CardTitle>
          </CardHeader>
          <CardContent>
            {severityData.length > 0 ? (
              <ResponsiveContainer width="100%" height={300}>
                <PieChart>
                  <Pie
                    data={severityData}
                    cx="50%"
                    cy="50%"
                    innerRadius={60}
                    outerRadius={100}
                    paddingAngle={2}
                    dataKey="value"
                    nameKey="name"
                    label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                    labelLine={false}
                  >
                    {severityData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{
                      backgroundColor: 'hsl(var(--popover))',
                      border: '1px solid hsl(var(--border))',
                      borderRadius: '8px',
                    }}
                  />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <p className="text-muted-foreground text-center py-8">No alert data available</p>
            )}
          </CardContent>
        </Card>

        <Card className="col-span-3 lg:col-span-2">
          <CardHeader>
            <CardTitle>Endpoint Health</CardTitle>
          </CardHeader>
          <CardContent>
            {statusData.length > 0 ? (
              <ResponsiveContainer width="100%" height={300}>
                <PieChart>
                  <Pie
                    data={statusData}
                    cx="50%"
                    cy="50%"
                    innerRadius={60}
                    outerRadius={100}
                    paddingAngle={2}
                    dataKey="value"
                    nameKey="name"
                    label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                    labelLine={false}
                  >
                    {statusData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{
                      backgroundColor: 'hsl(var(--popover))',
                      border: '1px solid hsl(var(--border))',
                      borderRadius: '8px',
                    }}
                  />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <p className="text-muted-foreground text-center py-8">No endpoint data available</p>
            )}
          </CardContent>
        </Card>

        <Card className="col-span-4 lg:col-span-3">
          <CardHeader>
            <CardTitle>Endpoints by OS</CardTitle>
          </CardHeader>
          <CardContent>
            {osData.length > 0 ? (
              <ResponsiveContainer width="100%" height={250}>
                <BarChart data={osData} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                  <XAxis type="number" stroke="hsl(var(--muted-foreground))" fontSize={12} />
                  <YAxis type="category" dataKey="os" width={120} stroke="hsl(var(--muted-foreground))" fontSize={12} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: 'hsl(var(--popover))',
                      border: '1px solid hsl(var(--border))',
                      borderRadius: '8px',
                    }}
                  />
                  <Bar dataKey="count" fill="hsl(var(--primary))" radius={[0, 4, 4, 0]} maxBarSize={32} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <p className="text-muted-foreground text-center py-8">No OS data available</p>
            )}
          </CardContent>
        </Card>

        <Card className="col-span-3 lg:col-span-2">
          <CardHeader>
            <CardTitle>Recent Alerts</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-muted-foreground text-center py-8">Recent alerts feed - connect to real-time WebSocket for live updates</p>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

export default DashboardPage
