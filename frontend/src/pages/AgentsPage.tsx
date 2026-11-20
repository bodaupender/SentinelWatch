"use client"

import { useState } from 'react'
import { Search, MoreHorizontal, Wifi, WifiOff, AlertCircle, Server, Activity } from 'lucide-react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Button } from '@components/ui/button'
import { Input } from '@components/ui/input'
import { Card, CardContent, CardHeader, CardTitle } from '@components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@components/ui/table'
import { Badge } from '@components/ui/badge'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@components/ui/dropdown-menu'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@components/ui/select'
import { Skeleton } from '@components/ui/skeleton'
import api from '@lib/api'
import { formatRelativeTime } from '@lib/utils'
import { toast } from 'sonner'
import { EnrollAgentHelp } from '@components/EnrollAgentHelp'

interface Agent {
  id: string
  hostname: string
  machine_guid: string
  os_version: string
  agent_version: string
  ip_address: string | null
  status: 'online' | 'offline' | 'stale' | 'unregistered'
  last_seen: string | null
  last_heartbeat: string | null
  config_version: number
  tags: string | null
  created_at: string
  updated_at: string
}

interface AgentListResponse {
  data: Agent[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export function AgentsPage() {
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [sort, setSort] = useState<'last_seen' | 'hostname' | 'status' | 'os_version'>('last_seen')
  const [order, setOrder] = useState<'asc' | 'desc'>('desc')
  const queryClient = useQueryClient()

  const { data: agentsResponse, isLoading, error, refetch } = useQuery<AgentListResponse, Error>({
    queryKey: ['agents', 'list', page.toString(), '50', search, statusFilter, sort, order],
    queryFn: async () => {
      const params = new URLSearchParams({
        page: page.toString(),
        limit: '50',
        sort,
        order,
        ...(search && { search }),
        ...(statusFilter !== 'all' && { status: statusFilter }),
      })
      const response = await api.get<AgentListResponse>(`/api/v1/agents?${params.toString()}`)
      return response.data
    },
    placeholderData: { data: [], total: 0, page: 1, page_size: 50, total_pages: 1 },
    refetchInterval: 30_000,
  })

  const deleteMutation = useMutation({
    mutationFn: async (id: string) => {
      const response = await api.delete(`/api/v1/agents/${id}`)
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agents'] })
      toast.success('Agent unenrolled')
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to unenroll agent')
    },
  })

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
      <div className="space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">Agents</h1>
            <p className="text-muted-foreground">Manage and monitor enrolled endpoints</p>
          </div>
          <EnrollAgentHelp />
        </div>
        <Card>
          <CardHeader>
            <CardTitle>Enrolled Agents (loading...)</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="table-container">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Hostname</TableHead>
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
                  {[...Array(5)].map((_, i) => (
                    <TableRow key={i}>
                      <TableCell><Skeleton className="h-4 w-32" /></TableCell>
                      <TableCell><Skeleton className="h-4 w-24" /></TableCell>
                      <TableCell><Skeleton className="h-4 w-36" /></TableCell>
                      <TableCell><Skeleton className="h-4 w-16" /></TableCell>
                      <TableCell><Skeleton className="h-4 w-20" /></TableCell>
                      <TableCell><Skeleton className="h-4 w-24" /></TableCell>
                      <TableCell><Skeleton className="h-4 w-28" /></TableCell>
                      <TableCell><Skeleton className="h-4 w-12" /></TableCell>
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
            <h1 className="text-3xl font-bold tracking-tight">Agents</h1>
            <p className="text-muted-foreground">Manage and monitor enrolled endpoints</p>
          </div>
        </div>
        <Card>
          <CardContent className="text-center py-8">
            <Server className="mx-auto h-12 w-12 text-destructive" />
            <h2 className="mt-4 text-xl font-semibold">Failed to load agents</h2>
            <p className="mt-2 text-muted-foreground">{error.message || 'Unknown error'}</p>
            <Button className="mt-4" onClick={() => refetch()}>Retry</Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  const agentsData = agentsResponse as AgentListResponse

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Agents</h1>
          <p className="text-muted-foreground">Manage and monitor enrolled endpoints</p>
        </div>
        <EnrollAgentHelp />
      </div>

      <Card>
        <CardHeader>
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            <CardTitle>Enrolled Agents ({agentsResponse?.total ?? 0})</CardTitle>
            <div className="flex items-center gap-2">
              <div className="relative w-64">
                <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  placeholder="Search agents..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  className="pl-10 w-64"
                />
              </div>
              <Select value={statusFilter} onValueChange={setStatusFilter}>
                <SelectTrigger className="w-40">
                  <SelectValue placeholder="All Status" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Status</SelectItem>
                  <SelectItem value="online">Online</SelectItem>
                  <SelectItem value="offline">Offline</SelectItem>
                  <SelectItem value="stale">Stale</SelectItem>
                  <SelectItem value="unregistered">Unregistered</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="table-container">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead onClick={() => handleSort('hostname')} className="cursor-pointer select-none">Hostname</TableHead>
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
                {agentsData.data?.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={8} className="text-center py-8 text-muted-foreground">No agents found</TableCell>
                  </TableRow>
                ) : (
                  agentsData.data?.map((agent) => (
                    <TableRow key={agent.id}>
                      <TableCell className="font-medium">{agent.hostname}</TableCell>
                      <TableCell>{agent.ip_address || 'N/A'}</TableCell>
                      <TableCell>{agent.os_version}</TableCell>
                      <TableCell>{agent.agent_version}</TableCell>
                      <TableCell>{getStatusBadge(agent.status)}</TableCell>
                      <TableCell>{agent.last_seen ? formatRelativeTime(agent.last_seen) : 'Never'}</TableCell>
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
                            <DropdownMenuItem onClick={() => window.location.href = `/endpoints`}>
                              <Server className="mr-2 h-4 w-4" />
                              View Details
                            </DropdownMenuItem>
                            <DropdownMenuItem onClick={() => window.location.href = `/processes?agent_id=${agent.id}`}>
                              <Activity className="mr-2 h-4 w-4" />
                              View Processes
                            </DropdownMenuItem>
                            <DropdownMenuItem onClick={() => window.location.href = `/services?agent_id=${agent.id}`}>
                              <Server className="mr-2 h-4 w-4" />
                              View Services
                            </DropdownMenuItem>
                            <DropdownMenuItem onClick={() => window.location.href = `/alerts?agent_id=${agent.id}`}>
                              <svg className="mr-2 h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                              View Alerts
                            </DropdownMenuItem>
                            <DropdownMenuItem className="text-destructive" onClick={() => deleteMutation.mutate(agent.id)} disabled={deleteMutation.isPending}>
                              <svg className="mr-2 h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                              Unenroll
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
              Showing {(page - 1) * 50 + 1} to {Math.min(page * 50, agentsData.total ?? 0)} of {agentsData.total ?? 0} results
            </p>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1 || isLoading}>
                <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" /></svg>
              </Button>
              <Button variant="outline" size="sm" onClick={() => setPage(p => p + 1)} disabled={page >= (agentsData.total_pages ?? 1) || isLoading}>
                <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" /></svg>
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

export default AgentsPage
