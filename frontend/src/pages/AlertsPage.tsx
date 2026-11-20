"use client"

import { useState } from 'react'
import { Search, MoreHorizontal, AlertTriangle, CheckCircle, XCircle, Shield, Flag, ChevronLeft, ChevronRight } from 'lucide-react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from '@components/ui/card'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@components/ui/table'
import { Input } from '@components/ui/input'
import { Badge } from '@components/ui/badge'
import { Button } from '@components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator,
} from '@components/ui/dropdown-menu'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@components/ui/select'
import { Skeleton } from '@components/ui/skeleton'
import { cn } from '@lib/utils'
import api from '@lib/api'
import { formatRelativeTime } from '@lib/utils'
import { toast } from 'sonner'

interface Alert {
  id: string
  agent_id: string
  agent_hostname: string | null
  rule_id: string | null
  rule_name: string | null
  severity: 'critical' | 'high' | 'medium' | 'low' | 'info'
  status: 'new' | 'investigating' | 'true_positive' | 'false_positive' | 'benign' | 'resolved' | 'suppressed'
  mitre_techniques: string[] | null
  mitre_tactics: string[] | null
  correlation_key: string | null
  finding_count: number
  summary: string
  description: string | null
  evidence_id: string | null
  assignee: string | null
  triage_notes: string | null
  triaged_at: string | null
  resolution: string | null
  resolution_notes: string | null
  resolved_at: string | null
  resolved_by: string | null
  created_at: string
  updated_at: string
}

interface AlertListResponse {
  data: Alert[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

const validStatuses = ['new', 'investigating', 'true_positive', 'false_positive', 'benign', 'resolved', 'suppressed'] as const
const validSeverities = ['critical', 'high', 'medium', 'low', 'info'] as const

export function AlertsPage() {
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [severityFilter, setSeverityFilter] = useState<string>('all')
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [sort, setSort] = useState<'created_at' | 'severity' | 'status'>('created_at')
  const [order, setOrder] = useState<'asc' | 'desc'>('desc')
  const queryClient = useQueryClient()

  const { data: alertsResponse, isLoading, error, refetch } = useQuery<AlertListResponse, Error>({
    queryKey: ['alerts', 'list', page.toString(), '50', search, severityFilter, statusFilter, sort, order],
    queryFn: async () => {
      const params = new URLSearchParams({
        page: page.toString(),
        limit: '50',
        sort,
        order,
        ...(search && { search }),
        ...(severityFilter !== 'all' && { severity: severityFilter }),
        ...(statusFilter !== 'all' && { status_filter: statusFilter }),
      })
      const response = await api.get<AlertListResponse>(`/api/v1/alerts?${params.toString()}`)
      return response.data
    },
    placeholderData: { data: [], total: 0, page: 1, page_size: 50, total_pages: 1 },
    refetchInterval: 30_000,
  })

  const triageMutation = useMutation({
    mutationFn: async ({ id, status, assignee, notes }: { id: string; status: string; assignee?: string; notes?: string }) => {
      const response = await api.post(`/api/v1/alerts/${id}/triage`, { status, assignee, notes })
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alerts'] })
      toast.success('Alert triaged successfully')
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to triage alert')
    },
  })

  const resolveMutation = useMutation({
    mutationFn: async ({ id, resolution, notes }: { id: string; resolution: string; notes?: string }) => {
      const response = await api.post(`/api/v1/alerts/${id}/resolve`, { resolution, notes })
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alerts'] })
      toast.success('Alert resolved successfully')
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to resolve alert')
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

  const getSeverityBadge = (severity: string) => {
    const variants: Record<string, string> = {
      critical: 'badge-critical',
      high: 'badge-high',
      medium: 'badge-medium',
      low: 'badge-low',
      info: 'badge-info',
    }
    return <Badge className={cn('badge', variants[severity])}>{severity.charAt(0).toUpperCase() + severity.slice(1)}</Badge>
  }

  const getStatusBadge = (status: string) => {
    const variants: Record<string, string> = {
      new: 'badge-high',
      investigating: 'badge-medium',
      true_positive: 'badge-success',
      false_positive: 'badge-low',
      benign: 'badge-low',
      resolved: 'badge-success',
      suppressed: 'badge-info',
    }
    return <Badge className={cn('badge', variants[status])}>{status.replace('_', ' ').toUpperCase()}</Badge>
  }

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">Alerts</h1>
            <p className="text-muted-foreground">Triage and investigate security alerts</p>
          </div>
        </div>
        <Card>
          <CardHeader>
            <CardTitle>Alerts (loading...)</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="table-container">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Time</TableHead>
                    <TableHead>Agent</TableHead>
                    <TableHead>Rule</TableHead>
                    <TableHead>MITRE</TableHead>
                    <TableHead>Severity</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {[...Array(5)].map((_, i) => (
                    <TableRow key={i}>
                      <TableCell><Skeleton className="h-4 w-20" /></TableCell>
                      <TableCell><Skeleton className="h-4 w-32" /></TableCell>
                      <TableCell><Skeleton className="h-4 w-40" /></TableCell>
                      <TableCell><Skeleton className="h-4 w-16" /></TableCell>
                      <TableCell><Skeleton className="h-4 w-20" /></TableCell>
                      <TableCell><Skeleton className="h-4 w-24" /></TableCell>
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
            <h1 className="text-3xl font-bold tracking-tight">Alerts</h1>
            <p className="text-muted-foreground">Triage and investigate security alerts</p>
          </div>
        </div>
        <Card>
          <CardContent className="text-center py-8">
            <AlertTriangle className="mx-auto h-12 w-12 text-destructive" />
            <h2 className="mt-4 text-xl font-semibold">Failed to load alerts</h2>
            <p className="mt-2 text-muted-foreground">{error.message || 'Unknown error'}</p>
            <Button className="mt-4" onClick={() => refetch()}>Retry</Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  const alertsData = alertsResponse as AlertListResponse

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Alerts</h1>
          <p className="text-muted-foreground">Triage and investigate security alerts</p>
        </div>
      </div>

      <Card>
        <CardHeader>
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            <CardTitle>Alerts ({alertsResponse?.total ?? 0})</CardTitle>
            <div className="flex flex-wrap items-center gap-2">
              <div className="relative w-64">
                <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  placeholder="Search alerts..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  className="pl-10"
                />
              </div>
              <Select value={severityFilter} onValueChange={setSeverityFilter}>
                <SelectTrigger className="w-36">
                  <SelectValue placeholder="All Severity" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Severity</SelectItem>
                  {validSeverities.map(s => <SelectItem key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</SelectItem>)}
                </SelectContent>
              </Select>
              <Select value={statusFilter} onValueChange={setStatusFilter}>
                <SelectTrigger className="w-40">
                  <SelectValue placeholder="All Status" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Status</SelectItem>
                  {validStatuses.map(s => <SelectItem key={s} value={s}>{s.replace('_', ' ').toUpperCase()}</SelectItem>)}
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
                  <TableHead onClick={() => handleSort('created_at')} className="cursor-pointer select-none">Time</TableHead>
                  <TableHead>Agent</TableHead>
                  <TableHead>Rule</TableHead>
                  <TableHead>MITRE</TableHead>
                  <TableHead onClick={() => handleSort('severity')} className="cursor-pointer select-none">Severity</TableHead>
                  <TableHead onClick={() => handleSort('status')} className="cursor-pointer select-none">Status</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {alertsData.data?.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={7} className="text-center py-8 text-muted-foreground">No alerts found</TableCell>
                  </TableRow>
                ) : (
                  alertsData.data?.map((alert) => (
                    <TableRow key={alert.id}>
                      <TableCell className="font-mono text-sm">{formatRelativeTime(alert.created_at)}</TableCell>
                      <TableCell className="font-medium">{alert.agent_hostname || alert.agent_id}</TableCell>
                      <TableCell>{alert.rule_name || alert.rule_id || 'Unknown'}</TableCell>
                      <TableCell>
                        <code className="text-xs text-muted-foreground">{alert.mitre_techniques?.join(', ') || '—'}</code>
                      </TableCell>
                      <TableCell>{getSeverityBadge(alert.severity)}</TableCell>
                      <TableCell>{getStatusBadge(alert.status)}</TableCell>
                      <TableCell className="text-right">
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button variant="ghost" size="icon" className="h-8 w-8">
                              <MoreHorizontal className="h-4 w-4" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuItem onClick={() => window.location.href = `/alert/${alert.id}`}>
                              <Search className="mr-2 h-4 w-4" />
                              View Evidence
                            </DropdownMenuItem>
                            <DropdownMenuItem onClick={() => window.location.href = `/alert/${alert.id}`}>
                              <Flag className="mr-2 h-4 w-4" />
                              Start Investigation
                            </DropdownMenuItem>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem
                              onClick={() => triageMutation.mutate({ id: alert.id, status: 'investigating', notes: 'Started investigation' })}
                              disabled={triageMutation.isPending}
                            >
                              <Flag className="mr-2 h-4 w-4" />
                              Mark Investigating
                            </DropdownMenuItem>
                            <DropdownMenuItem
                              onClick={() => triageMutation.mutate({ id: alert.id, status: 'true_positive' })}
                              disabled={triageMutation.isPending}
                            >
                              <CheckCircle className="mr-2 h-4 w-4" />
                              Mark True Positive
                            </DropdownMenuItem>
                            <DropdownMenuItem
                              onClick={() => triageMutation.mutate({ id: alert.id, status: 'false_positive' })}
                              disabled={triageMutation.isPending}
                            >
                              <XCircle className="mr-2 h-4 w-4" />
                              Mark False Positive
                            </DropdownMenuItem>
                            <DropdownMenuItem
                              onClick={() => triageMutation.mutate({ id: alert.id, status: 'suppressed' })}
                              disabled={triageMutation.isPending}
                            >
                              <Shield className="mr-2 h-4 w-4" />
                              Suppress
                            </DropdownMenuItem>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem
                              onClick={() => resolveMutation.mutate({ id: alert.id, resolution: 'true_positive' })}
                              disabled={resolveMutation.isPending}
                            >
                              <Shield className="mr-2 h-4 w-4" />
                              Resolve as True Positive
                            </DropdownMenuItem>
                            <DropdownMenuItem
                              onClick={() => resolveMutation.mutate({ id: alert.id, resolution: 'false_positive' })}
                              disabled={resolveMutation.isPending}
                            >
                              <XCircle className="mr-2 h-4 w-4" />
                              Resolve as False Positive
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
              Showing {(page - 1) * 50 + 1} to {Math.min(page * 50, alertsData.total ?? 0)} of {alertsData.total ?? 0} results
            </p>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1 || isLoading}>
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <Button variant="outline" size="sm" onClick={() => setPage(p => p + 1)} disabled={page >= (alertsData.total_pages ?? 1) || isLoading}>
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

export default AlertsPage
