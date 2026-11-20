import { useState } from 'react'
import { AlertTriangle, AlertTriangle as AlertTriangleIcon2, Shield, Clock, CheckCircle, XCircle, MoreHorizontal, Server, Download, Calendar, FileText } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@components/ui/card'
import { Label } from '@components/ui/label'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@components/ui/table'
import { Input } from '@components/ui/input'
import { Badge } from '@components/ui/badge'
import { Button } from '@components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@components/ui/select'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@components/ui/tabs'
import api from '@lib/api'
import { formatDate, formatRelativeTime } from '@lib/utils'
import {
  BarChart as RechartsBarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  LineChart,
  Line,
} from 'recharts'

interface AlertReport {
  total_alerts: number
  by_severity: Record<string, number>
  by_status: Record<string, number>
  by_agent: Record<string, number>
  by_rule: Record<string, number>
  timeline: Array<{ hour: string; count: number }>
}

interface EndpointReport {
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
  new: '#ef4444',
  investigating: '#f97316',
  true_positive: '#22c55e',
  false_positive: '#3b82f6',
  benign: '#6b7280',
  resolved: '#22c55e',
  suppressed: '#6b7280',
}

export function ReportsPage() {
  const [activeTab, setActiveTab] = useState<string>('alerts')
  const [dateRange, setDateRange] = useState<{ from: Date | undefined; to: Date | undefined }>({
    from: new Date(Date.now() - 7 * 24 * 60 * 60 * 1000),
    to: new Date(),
  })

  const { data: alertReport, isLoading: alertLoading } = useQuery<AlertReport>({
    queryKey: ['reports', 'alerts', { from: dateRange?.from?.toISOString(), to: dateRange?.to?.toISOString() }],
    queryFn: async () => {
      const params = new URLSearchParams({
        start_time: dateRange.from?.toISOString() || '',
        end_time: dateRange.to?.toISOString() || '',
      })
      const response = await api.get(`/api/v1/reports/alerts?${params.toString()}`)
      return response.data
    },
  })

  const { data: endpointReport, isLoading: endpointLoading } = useQuery<EndpointReport>({
    queryKey: ['reports', 'endpoints'],
    queryFn: async () => {
      const response = await api.get('/api/v1/reports/endpoints')
      return response.data
    },
  })

  const formatNumber = (num: number) => new Intl.NumberFormat().format(num)

  const severityData = [
    { name: 'Critical', value: alertReport?.by_severity?.critical || 0, color: SEVERITY_COLORS.critical },
    { name: 'High', value: alertReport?.by_severity?.high || 0, color: SEVERITY_COLORS.high },
    { name: 'Medium', value: alertReport?.by_severity?.medium || 0, color: SEVERITY_COLORS.medium },
    { name: 'Low', value: alertReport?.by_severity?.low || 0, color: SEVERITY_COLORS.low },
    { name: 'Info', value: alertReport?.by_severity?.info || 0, color: SEVERITY_COLORS.info },
  ].filter(d => d.value > 0)

  const statusData = Object.entries(alertReport?.by_status || {}).map(([status, count]) => ({
    name: status.replace('_', ' ').toUpperCase(),
    value: count,
    color: STATUS_COLORS[status as keyof typeof STATUS_COLORS] || '#6b7280',
  })).filter(d => d.value > 0)

  const timelineData = alertReport?.timeline?.map((t: any) => ({
    time: new Date(t.hour).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' }),
    count: t.count,
  })) ?? []

  const osData = Object.entries(endpointReport?.by_os || {}).map(([os, count]) => ({ os, count }))

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Reports</h1>
          <p className="text-muted-foreground">Generate and export security reports</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm">
            <Download className="mr-2 h-4 w-4" />
            Export All
          </Button>
        </div>
      </div>

      <div className="flex flex-col sm:flex-row gap-4 mb-6">
        <div className="relative w-48">
          <Calendar className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input
            type="date"
            value={dateRange.from?.toISOString().split('T')[0] || ''}
            onChange={(e) => setDateRange({ ...dateRange, from: e.target.value ? new Date(e.target.value) : undefined })}
            className="pl-10 h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
          />
        </div>
        <div className="relative w-48">
          <Calendar className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input
            type="date"
            value={dateRange.to?.toISOString().split('T')[0] || ''}
            onChange={(e) => setDateRange({ ...dateRange, to: e.target.value ? new Date(e.target.value) : undefined })}
            className="pl-10 h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
          />
        </div>
        <Button variant="outline" onClick={() => setDateRange({ from: new Date(Date.now() - 7 * 24 * 60 * 60 * 1000), to: new Date() })}>
          Last 7 Days
        </Button>
        <Button variant="outline" onClick={() => setDateRange({ from: new Date(Date.now() - 30 * 24 * 60 * 60 * 1000), to: new Date() })}>
          Last 30 Days
        </Button>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
        <TabsList className="grid w-full grid-cols-4">
          <TabsTrigger value="alerts"><AlertTriangleIcon2 className="mr-2 h-4 w-4" /> Alerts</TabsTrigger>
          <TabsTrigger value="endpoints"><Server className="mr-2 h-4 w-4" /> Endpoints</TabsTrigger>
          <TabsTrigger value="investigation"><FileText className="mr-2 h-4 w-4" /> Investigation</TabsTrigger>
          <TabsTrigger value="audit"><FileText className="mr-2 h-4 w-4" /> Audit</TabsTrigger>
        </TabsList>

        <TabsContent value="alerts" className="space-y-6">
          {alertLoading ? (
            <div className="flex h-64 items-center justify-center">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
            </div>
          ) : (
            <>
              <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4 mb-6">
                <Card>
                  <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle className="text-sm font-medium">Total Alerts</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="text-3xl font-bold">{formatNumber(alertReport?.total_alerts || 0)}</div>
                    <p className="text-xs text-muted-foreground">Total alerts in period</p>
                  </CardContent>
                </Card>
                <Card>
                  <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle className="text-sm font-medium">Critical</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="text-3xl font-bold text-red-500">{formatNumber(alertReport?.by_severity?.critical || 0)}</div>
                    <p className="text-xs text-muted-foreground">Critical severity</p>
                  </CardContent>
                </Card>
                <Card>
                  <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle className="text-sm font-medium">High</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="text-3xl font-bold text-orange-500">{formatNumber(alertReport?.by_severity?.high || 0)}</div>
                    <p className="text-xs text-muted-foreground">High severity</p>
                  </CardContent>
                </Card>
                <Card>
                  <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle className="text-sm font-medium">Medium</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="text-3xl font-bold text-yellow-500">{formatNumber(alertReport?.by_severity?.medium || 0)}</div>
                    <p className="text-xs text-muted-foreground">Medium severity</p>
                  </CardContent>
                </Card>
              </div>

              <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-7">
                <Card className="col-span-4 lg:col-span-3">
                  <CardHeader>
                    <CardTitle>Alert Timeline</CardTitle>
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
                          dataKey="count"
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
                    <CardTitle>Alerts by Status</CardTitle>
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
                      <p className="text-muted-foreground text-center py-8">No status data available</p>
                    )}
                  </CardContent>
                </Card>
              </div>
            </>
          )}
        </TabsContent>

        <TabsContent value="endpoints" className="space-y-6">
          {endpointLoading ? (
            <div className="flex h-64 items-center justify-center">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
            </div>
          ) : (
            <>
              <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4 mb-6">
                <Card>
                  <CardHeader>
                    <CardTitle>Enrolled Endpoints</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="text-3xl font-bold">{formatNumber(endpointReport?.enrolled_endpoints ?? endpointReport?.total_endpoints ?? 0)}</div>
                    <p className="text-xs text-muted-foreground">Total enrolled endpoints</p>
                  </CardContent>
                </Card>
                <Card>
                  <CardHeader>
                    <CardTitle>Online</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="text-3xl font-bold text-green-500">{formatNumber(endpointReport?.by_status?.online || 0)}</div>
                    <p className="text-xs text-muted-foreground">Online endpoints</p>
                  </CardContent>
                </Card>
                <Card>
                  <CardHeader>
                    <CardTitle>Offline</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="text-3xl font-bold text-red-500">{formatNumber(endpointReport?.by_status?.offline || 0)}</div>
                    <p className="text-xs text-muted-foreground">Offline endpoints</p>
                  </CardContent>
                </Card>
                <Card>
                  <CardHeader>
                    <CardTitle>Stale</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="text-3xl font-bold text-yellow-500">{formatNumber(endpointReport?.by_status?.stale || 0)}</div>
                    <p className="text-xs text-muted-foreground">Stale endpoints</p>
                  </CardContent>
                </Card>
              </div>

              <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-7">
                <Card className="col-span-4 lg:col-span-3">
                  <CardHeader>
                    <CardTitle>Endpoints by OS</CardTitle>
                  </CardHeader>
                  <CardContent>
                    {osData.length > 0 ? (
                      <ResponsiveContainer width="100%" height={300}>
                        <RechartsBarChart data={osData} layout="vertical">
                          <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                          <XAxis type="number" stroke="hsl(var(--muted-foreground))" fontSize={12} />
                          <YAxis type="category" dataKey="os" width={150} stroke="hsl(var(--muted-foreground))" fontSize={12} />
                          <Tooltip
                            contentStyle={{
                              backgroundColor: 'hsl(var(--popover))',
                              border: '1px solid hsl(var(--border))',
                              borderRadius: '8px',
                            }}
                          />
                          <Bar dataKey="count" fill="hsl(var(--primary))" radius={[0, 4, 4, 0]} maxBarSize={32} />
                        </RechartsBarChart>
                      </ResponsiveContainer>
                    ) : (
                      <p className="text-muted-foreground text-center py-8">No OS data available</p>
                    )}
                  </CardContent>
                </Card>

                <Card className="col-span-3 lg:col-span-2">
                  <CardHeader>
                    <CardTitle>Endpoints by Version</CardTitle>
                  </CardHeader>
                  <CardContent>
                    {Object.keys(endpointReport?.by_version || {}).length > 0 ? (
                      <ResponsiveContainer width="100%" height={300}>
                        <PieChart>
                          <Pie
                            data={Object.entries(endpointReport?.by_version || {}).map(([version, count]) => ({ version, count }))}
                            cx="50%"
                            cy="50%"
                            innerRadius={60}
                            outerRadius={100}
                            paddingAngle={2}
                            dataKey="count"
                            nameKey="version"
                            label={({ version, percent }) => `${version} ${(percent * 100).toFixed(0)}%`}
                            labelLine={false}
                          >
                            {Object.entries(endpointReport?.by_version || {}).map((_, index) => (
                              <Cell key={`cell-${index}`} fill={`hsl(var(--chart-${index}))`} />
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
                      <p className="text-muted-foreground text-center py-8">No version data available</p>
                    )}
                  </CardContent>
                </Card>

                <Card className="col-span-4 lg:col-span-3">
                  <CardHeader>
                    <CardTitle>Alerts per Endpoint (Last 7 Days)</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-3 max-h-96 overflow-y-auto">
                      {Object.entries(endpointReport?.alerts_per_endpoint || {})
                        .sort(([, a], [, b]) => b - a)
                        .slice(0, 20)
                        .map(([agent, count]) => (
                          <div key={agent} className="flex items-center justify-between">
                            <span className="text-sm truncate max-w-xs">{agent}</span>
                            <Badge variant="secondary">{count}</Badge>
                          </div>
                        ))}
                      {Object.keys(endpointReport?.alerts_per_endpoint || {}).length === 0 && (
                        <p className="text-muted-foreground text-center py-4">No alert data available</p>
                      )}
                    </div>
                  </CardContent>
                </Card>
              </div>
            </>
          )}
        </TabsContent>

        <TabsContent value="investigation" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Investigation Export</CardTitle>
              <CardDescription>Export detailed investigation data for a specific alert</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-4">
                <div>
                  <Label htmlFor="investigation-alert-id">Alert ID</Label>
                  <Input
                    placeholder="Enter alert ID to export investigation"
                    className="w-full max-w-md"
                  />
                </div>
                <Button variant="outline" className="w-full max-w-md">
                  <Download className="mr-2 h-4 w-4" />
                  Export Investigation
                </Button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="audit" className="space-y-6">
          <Card>
            <CardHeader className="flex flex-row sm:flex-row sm:items-center sm:justify-between">
              <CardTitle>Audit Log Export</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex flex-col sm:flex-row gap-4">
                <div className="relative w-48">
                  <Calendar className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                  <input
                    type="date"
                    className="pl-10 h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                  />
                </div>
                <div className="relative w-48">
                  <Calendar className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                  <input
                    type="date"
                    className="pl-10 h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                  />
                </div>
                <Button variant="outline">
                  <Download className="mr-2 h-4 w-4" />
                  Export CSV
                </Button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}

export default ReportsPage
