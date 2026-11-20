import { useState } from 'react'
import { Server, Search, Filter, FilterX, Wifi, WifiOff, AlertCircle, MoreHorizontal, Download, Shield, Cpu, ServerCog, ChevronLeft, ChevronRight } from 'lucide-react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@components/ui/table'
import { Input } from '@components/ui/input'
import { Badge } from '@components/ui/badge'
import { Button } from '@components/ui/button'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@components/ui/dropdown-menu'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@components/ui/select'
import { cn } from '@lib/utils'
import api from '@lib/api'
import { EnrollAgentHelp } from '@components/EnrollAgentHelp'
import { formatDate } from '@lib/utils'

interface AgentDetail {
  id: string
  hostname: string
  machine_guid: string
  os_version: string
  agent_version: string
  ip_address: string
  status: 'online' | 'offline' | 'stale' | 'unregistered'
  last_seen: string
  last_heartbeat: string
  config_version: number
  tags: string
  health_data: {
    cpu_percent: number
    memory_mb: number
    memory_percent: number
    disk_free_gb: number
    disk_total_gb: number
    network_bytes_sent: number
    network_bytes_recv: number
    queue_depth: number
    batches_sent: number
    batches_failed: number
    events_sent: number
    events_rejected: number
    last_heartbeat: string
    last_config_poll: string
  }
  health_alerts: string[]
}

interface AgentListResponse {
  data: AgentDetail[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export function EndpointManagementPage() {
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(50)
  const [sort, setSort] = useState<'last_seen' | 'hostname' | 'status' | 'os_version'>('last_seen')
  const [order, setOrder] = useState<'asc' | 'desc'>('desc')
  const [statusFilter, setStatusFilter] = useState('all')

  const { data: agentsResponse, isLoading, error } = useQuery<AgentListResponse>({
    queryKey: ['agents', page, pageSize, sort, order, statusFilter],
    queryFn: async () => {
      const params = new URLSearchParams({
        page: page.toString(),
        limit: pageSize.toString(),
        sort,
        order,
        ...(statusFilter !== 'all' && { status: statusFilter }),
      })
      const response = await api.get<AgentListResponse>(`/api/v1/agents?${params.toString()}`)
      return response.data
    },
    placeholderData: { data: [], total: 0, page: 1, page_size: 50, total_pages: 1 },
  })

  const filteredAgents = agentsResponse?.data || []

  const handleSort = (column: typeof sort) => {
    if (sort === column) {
      setOrder(order === 'asc' ? 'desc' : 'asc')
    } else {
      setSort(column)
      setOrder('asc')
    }
  }

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'online':
        return <Badge className="badge-online"><Wifi className="mr-1 h-3 w-3" /> Online</Badge>
      case 'offline':
        return <Badge className="badge-offline"><WifiOff className="mr-1 h-3 w-3" /> Offline</Badge>
      case 'stale':
        return <Badge className="badge-stale"><AlertCircle className="mr-1 h-3 w-3" /> Stale</Badge>
      case 'unregistered':
        return <Badge className="badge-offline">Unregistered</Badge>
      default:
        return <Badge>{status}</Badge>
    }
  }

  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Endpoint Management</h1>
          <p className="text-muted-foreground">Manage and monitor enrolled endpoints</p>
        </div>
        <div className="flex items-center gap-2">
          <EnrollAgentHelp />
        </div>
      </div>

      <Card>
        <CardHeader>
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            <CardTitle>Enrolled Agents ({agentsResponse?.data?.length || 0})</CardTitle>
            <div className="flex items-center gap-2">
              <div className="relative w-64">
                <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  placeholder="Search agents..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  className="pl-10"
                />
              </div>
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="flex h-10 w-40 items-center rounded-md border border-input bg-background px-3 py-2 text-sm"
              >
                <option value="all">All Status</option>
                <option value="online">Online</option>
                <option value="offline">Offline</option>
                <option value="stale">Stale</option>
              </select>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="table-container">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead onClick={() => handleSort('hostname')}>Hostname</TableHead>
                  <TableHead>IP Address</TableHead>
                  <TableHead>OS</TableHead>
                  <TableHead>Version</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Last Seen</TableHead>
                  <TableHead>Tags</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredAgents.map((agent) => (
                  <TableRow key={agent.id}>
                    <TableCell className="font-medium">{agent.hostname}</TableCell>
                    <TableCell>{agent.ip_address || 'N/A'}</TableCell>
                    <TableCell>{agent.os_version}</TableCell>
                    <TableCell>{agent.agent_version}</TableCell>
                    <TableCell>{getStatusBadge(agent.status)}</TableCell>
                    <TableCell>{formatRelativeTime(agent.last_seen)}</TableCell>
                    <TableCell>
                      <span className="text-sm text-muted-foreground">{agent.tags || '—'}</span>
                    </TableCell>
                    <TableCell className="text-right">
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon" className="h-8 w-8">
                            <MoreHorizontal className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem>View Details</DropdownMenuItem>
                          <DropdownMenuItem>View Processes</DropdownMenuItem>
                          <DropdownMenuItem>View Services</DropdownMenuItem>
                          <DropdownMenuItem>View Alerts</DropdownMenuItem>
                          <DropdownMenuItem className="text-destructive">Unenroll</DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          <div className="flex items-center justify-between mt-4">
            <p className="text-sm text-muted-foreground">
              Showing {(page - 1) * pageSize + 1} to {Math.min(page * pageSize, agentsResponse?.total || 0)} of {agentsResponse?.total || 0} results
            </p>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}>
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <Button variant="outline" size="sm" onClick={() => setPage(p => p + 1)} disabled={page >= (agentsResponse?.total_pages || 1)}>
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

function getStatusBadge(status: string) {
  switch (status) {
    case 'online':
      return <Badge className="badge-online"><Wifi className="mr-1 h-3 w-3" /> Online</Badge>
    case 'offline':
      return <Badge className="badge-offline"><WifiOff className="mr-1 h-3 w-3" /> Offline</Badge>
    case 'stale':
      return <Badge className="badge-stale"><AlertCircle className="mr-1 h-3 w-3" /> Stale</Badge>
    default:
      return <Badge>{status}</Badge>
  }
}

function formatRelativeTime(dateString: string) {
  const date = new Date(dateString)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffSecs = Math.floor(diffMs / 1000)
  const diffMins = Math.floor(diffSecs / 60)
  const diffHours = Math.floor(diffMins / 60)
  const diffDays = Math.floor(diffHours / 24)

  if (diffSecs < 60) return 'just now'
  if (diffMins < 60) return `${diffMins}m ago`
  if (diffHours < 24) return `${diffHours}h ago`
  if (diffDays < 7) return `${diffDays}d ago`
  return new Date(dateString).toLocaleDateString()
}

export default EndpointManagementPage
