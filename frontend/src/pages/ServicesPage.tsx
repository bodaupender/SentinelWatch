"use client"

import { useState } from 'react'
import { Search, ServerCog, Download, MoreHorizontal } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@components/ui/table'
import { Input } from '@components/ui/input'
import { Badge } from '@components/ui/badge'
import { Button } from '@components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@components/ui/select'
import { Skeleton } from '@components/ui/skeleton'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@components/ui/dropdown-menu'
import api from '@lib/api'

interface ServiceTelemetry {
  id: string
  agent_id: string
  agent_hostname: string | null
  collected_at: string
  sequence: number
  name: string
  display_name: string | null
  description: string | null
  status: string
  start_type: string
  pid: number | null
  binary_path: string | null
  service_type: string | null
  dependencies: string[] | null
  account: string | null
  exe_sha256: string | null
}

interface ServiceListResponse {
  data: ServiceTelemetry[]
  total: number
  page: number
  page_size: number
  total_pages: number
  snapshot_at?: string | null
  is_stale?: boolean
  stale_agents?: number
}

export function ServicesPage() {
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [sort, setSort] = useState<'collected_at' | 'name' | 'status' | 'start_type'>('collected_at')
  const [order, setOrder] = useState<'asc' | 'desc'>('desc')
  const [filters, setFilters] = useState({
    agent_id: '',
    status: '',
    start_type: '',
  })

  const filterString = JSON.stringify(filters)

  const { data: servicesResponse, isLoading, error, refetch } = useQuery<ServiceListResponse, Error>({
    queryKey: ['services', 'list', page.toString(), '50', sort, order, filterString, search] as string[],
    queryFn: async () => {
      const params = new URLSearchParams({
        page: page.toString(),
        limit: '50',
        sort,
        order,
        ...(filters.agent_id && { agent_id: filters.agent_id }),
        ...(filters.status && { status: filters.status }),
        ...(filters.start_type && { start_type: filters.start_type }),
        ...(search && { search }),
      })
      const response = await api.get<ServiceListResponse>(`/api/v1/telemetry/services?${params.toString()}`)
      return response.data
    },
    placeholderData: { data: [], total: 0, page: 1, page_size: 50, total_pages: 1 },
    refetchInterval: 60_000,
  })

  const handleSort = (column: typeof sort) => {
    if (sort === column) {
      setOrder(order === 'asc' ? 'desc' : 'asc')
    } else {
      setSort(column)
      setOrder('asc')
    }
  }

  const clearFilters = () => {
    setFilters({ agent_id: '', status: '', start_type: '' })
    setSearch('')
  }

  const getStatusBadge = (status: string) => {
    switch (status.toUpperCase()) {
      case 'RUNNING':
        return <Badge className="badge-success">Running</Badge>
      case 'STOPPED':
        return <Badge className="badge-offline">Stopped</Badge>
      case 'PAUSED':
        return <Badge className="badge-stale">Paused</Badge>
      case 'START_PENDING':
      case 'STOP_PENDING':
      case 'CONTINUE_PENDING':
      case 'PAUSE_PENDING':
        return <Badge className="badge-stale">Pending</Badge>
      default:
        return <Badge>{status}</Badge>
    }
  }

  const getStartTypeBadge = (type: string) => {
    const colors: Record<string, string> = {
      AUTO: 'badge-success',
      DELAYED_AUTO: 'badge-success',
      MANUAL: 'badge-stale',
      DISABLED: 'badge-offline',
    }
    return <Badge className={colors[type.toUpperCase()] || 'badge-info'}>{type}</Badge>
  }

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">Services</h1>
            <p className="text-muted-foreground">Monitor Windows services across endpoints</p>
          </div>
        </div>
        <Card>
          <CardHeader>
            <CardTitle>Services (loading...)</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="table-container">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Service Name</TableHead>
                    <TableHead>Display Name</TableHead>
                    <TableHead>PID</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Start Type</TableHead>
                    <TableHead>Binary Path</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {[...Array(5)].map((_, i) => (
                    <TableRow key={i}>
                      <TableCell><Skeleton className="h-4 w-24" /></TableCell>
                      <TableCell><Skeleton className="h-4 w-32" /></TableCell>
                      <TableCell><Skeleton className="h-4 w-12" /></TableCell>
                      <TableCell><Skeleton className="h-4 w-20" /></TableCell>
                      <TableCell><Skeleton className="h-4 w-20" /></TableCell>
                      <TableCell><Skeleton className="h-4 w-48" /></TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      </div>
    )
  }

  if (error) {
    return (
      <div className="space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">Services</h1>
            <p className="text-muted-foreground">Monitor Windows services across endpoints</p>
          </div>
        </div>
        <Card>
          <CardContent className="text-center py-8">
            <ServerCog className="mx-auto h-12 w-12 text-destructive" />
            <h2 className="mt-4 text-xl font-semibold">Failed to load services</h2>
            <p className="mt-2 text-muted-foreground">{error.message || 'Unknown error'}</p>
            <Button className="mt-4" onClick={() => refetch()}>Retry</Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  const servicesData = servicesResponse as ServiceListResponse
  const { data: agentResponse } = useQuery<{ data: { id: string; hostname: string; status: string }[] }>({
    queryKey: ['agents', 'service-filter'],
    queryFn: async () => (await api.get('/api/v1/agents?limit=100')).data,
  })

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Services</h1>
          <p className="text-muted-foreground">Monitor Windows services across endpoints</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => window.open('/api/v1/telemetry/services/export', '_blank')}>
            <Download className="mr-2 h-4 w-4" />
            Export CSV
          </Button>
        </div>
      </div>

      {/* Filters */}
      <Card className="mb-4">
        <CardContent className="pt-4">
          <div className="flex flex-col sm:flex-row gap-4">
            <div className="relative flex-1 max-w-md">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                placeholder="Search services..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="pl-10"
              />
            </div>
            <div className="relative w-48">
              <Select value={filters.agent_id || 'all'} onValueChange={(v) => setFilters({ ...filters, agent_id: v === 'all' ? '' : v })}>
                <SelectTrigger className="w-full"><SelectValue placeholder="All Endpoints" /></SelectTrigger>
                <SelectContent><SelectItem value="all">All Endpoints</SelectItem>{(agentResponse?.data ?? []).map((agent) => <SelectItem key={agent.id} value={agent.id}>{agent.hostname}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="relative w-48">
              <Select value={filters.status || 'all'} onValueChange={(v) => setFilters({ ...filters, status: v === 'all' ? '' : v })}>
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="All Status" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Status</SelectItem>
                  <SelectItem value="RUNNING">Running</SelectItem>
                  <SelectItem value="STOPPED">Stopped</SelectItem>
                  <SelectItem value="PAUSED">Paused</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="relative w-48">
              <Select value={filters.start_type || 'all'} onValueChange={(v) => setFilters({ ...filters, start_type: v === 'all' ? '' : v })}>
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="All Start Types" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Start Types</SelectItem>
                  <SelectItem value="AUTO">Auto</SelectItem>
                  <SelectItem value="DELAYED_AUTO">Delayed Auto</SelectItem>
                  <SelectItem value="MANUAL">Manual</SelectItem>
                  <SelectItem value="DISABLED">Disabled</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <Button variant="outline" size="sm" onClick={clearFilters}>
              <svg className="mr-2 h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z" /></svg>
              Clear Filters
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            <div><CardTitle>Current Services ({servicesData.total || 0})</CardTitle><p className="mt-1 text-xs text-muted-foreground">Distinct services from the latest collected snapshot{servicesData.snapshot_at ? ` · ${new Date(servicesData.snapshot_at).toLocaleString()}` : ''}</p></div>
            <div className="flex items-center gap-2">
              <Select value={sort} onValueChange={(v: string) => setSort(v as typeof sort)}>
                <SelectTrigger className="w-40">
                  <SelectValue placeholder="Sort by" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="collected_at">Collection Time</SelectItem>
                  <SelectItem value="name">Service Name</SelectItem>
                  <SelectItem value="status">Status</SelectItem>
                  <SelectItem value="start_type">Start Type</SelectItem>
                </SelectContent>
              </Select>
              <Button variant="outline" size="icon" onClick={() => setOrder(order === 'asc' ? 'desc' : 'asc')}>
                {order === 'asc' ? (
                  <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 15l7-7 7 7" /></svg>
                ) : (
                  <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" /></svg>
                )}
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {(servicesData.is_stale || (servicesData.stale_agents ?? 0) > 0) && <div className="mb-4 rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm">
            {servicesData.is_stale
              ? 'No recent service telemetry is available.'
              : `${servicesData.stale_agents} endpoint${servicesData.stale_agents === 1 ? '' : 's'} have stale service telemetry.`} Start or reconnect the SentinelWatch agent to refresh service data.
          </div>}
          <div className="table-container">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead onClick={() => handleSort('name')} className="cursor-pointer select-none">Service Name</TableHead>
                  <TableHead>Display Name</TableHead>
                  <TableHead>PID</TableHead>
                  <TableHead onClick={() => handleSort('status')} className="cursor-pointer select-none">Status</TableHead>
                  <TableHead onClick={() => handleSort('start_type')} className="cursor-pointer select-none">Start Type</TableHead>
                  <TableHead>Binary Path</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {servicesData.data?.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={7} className="text-center py-8 text-muted-foreground">
                      {servicesData.is_stale ? 'Service data is stale or unavailable.' : 'No services match the current filters.'}
                    </TableCell>
                  </TableRow>
                ) : (
                  servicesData.data?.map((svc) => (
                    <TableRow key={svc.id}>
                      <TableCell className="font-mono">{svc.name}</TableCell>
                      <TableCell>
                        <div>{svc.display_name || 'N/A'}</div>
                        {svc.description && <div className="max-w-[280px] truncate text-xs text-muted-foreground" title={svc.description}>{svc.description}</div>}
                      </TableCell>
                      <TableCell className="font-mono">{svc.pid ?? '—'}</TableCell>
                      <TableCell>{getStatusBadge(svc.status)}</TableCell>
                      <TableCell>{getStartTypeBadge(svc.start_type)}</TableCell>
                      <TableCell>
                        <code className="text-xs text-muted-foreground max-w-[400px] truncate block">{svc.binary_path || 'N/A'}</code>
                      </TableCell>
                      <TableCell className="text-right">
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button variant="ghost" size="icon" className="h-8 w-8">
                              <MoreHorizontal className="h-4 w-4" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuItem onClick={() => window.location.href = `/service/${svc.id}`}>
                              <Search className="mr-2 h-4 w-4" />
                              View Details
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>
          <div className="flex items-center justify-between mt-4">
            <p className="text-sm text-muted-foreground">
              Showing {(page - 1) * 50 + 1} to {Math.min(page * 50, servicesData.total || 0)} of {servicesData.total || 0} results
            </p>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1 || isLoading}>
                <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" /></svg>
              </Button>
              <Button variant="outline" size="sm" onClick={() => setPage(p => p + 1)} disabled={page >= (servicesData.total_pages || 1) || isLoading}>
                <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" /></svg>
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

export default ServicesPage
