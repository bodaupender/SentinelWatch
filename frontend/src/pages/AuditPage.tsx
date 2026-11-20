"use client"

import { useState } from 'react'
import { Search, Download, ChevronLeft, ChevronRight, AlertCircle } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@components/ui/table'
import { Input } from '@components/ui/input'
import { Badge } from '@components/ui/badge'
import { Button } from '@components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@components/ui/select'
import { Skeleton } from '@components/ui/skeleton'
import api from '@lib/api'
import { formatDate } from '@lib/utils'

interface AuditLog {
  id: string
  timestamp: string
  actor_type: 'user' | 'agent' | 'system'
  actor_id: string
  actor_name: string | null
  action: string
  resource_type: string | null
  resource_id: string | null
  details: Record<string, any> | null
  ip_address: string | null
  user_agent: string | null
  request_id: string | null
  result: 'success' | 'failure' | 'denied'
  error_message: string | null
}

interface AuditListResponse {
  data: AuditLog[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export function AuditPage() {
  const downloadAudit = async () => {
    const response = await api.get('/api/v1/audit/export/csv', { responseType: 'blob' })
    const url = URL.createObjectURL(response.data)
    const link = document.createElement('a')
    link.href = url
    link.download = 'sentinelwatch-audit.csv'
    link.click()
    URL.revokeObjectURL(url)
  }
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [pageSize] = useState(50)
  const [actionFilter, setActionFilter] = useState('all')
  const [resultFilter, setResultFilter] = useState('all')
  const [actorTypeFilter, setActorTypeFilter] = useState('all')

  const { data: auditResponse, isLoading, error, refetch } = useQuery<AuditListResponse, Error>({
    queryKey: ['audit', 'list', page.toString(), '50', search, actionFilter, resultFilter, actorTypeFilter],
    queryFn: async () => {
      const params = new URLSearchParams({
        page: page.toString(),
        limit: '50',
        ...(search && { search }),
        ...(actionFilter !== 'all' && { action: actionFilter }),
        ...(resultFilter !== 'all' && { result: resultFilter }),
        ...(actorTypeFilter !== 'all' && { actor_type: actorTypeFilter }),
      })
      const response = await api.get<AuditListResponse>(`/api/v1/audit?${params.toString()}`)
      return response.data
    },
    placeholderData: { data: [], total: 0, page: 1, page_size: 50, total_pages: 1 },
    refetchInterval: 30_000,
  })

  const getResultBadge = (result: string) => {
    switch (result) {
      case 'success':
        return <Badge className="badge-success">Success</Badge>
      case 'failure':
        return <Badge className="badge-critical">Failure</Badge>
      case 'denied':
        return <Badge className="badge-high">Denied</Badge>
      default:
        return <Badge>{result}</Badge>
    }
  }

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">Audit Log</h1>
            <p className="text-muted-foreground">Review administrative and system actions</p>
          </div>
          <Button variant="outline" size="sm" onClick={downloadAudit}>
            <Download className="mr-2 h-4 w-4" />
            Export
          </Button>
        </div>
        <Card>
          <CardHeader>
            <CardTitle>Audit Entries (loading...)</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="table-container">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Timestamp</TableHead>
                    <TableHead>Actor</TableHead>
                    <TableHead>Action</TableHead>
                    <TableHead>Resource</TableHead>
                    <TableHead>Result</TableHead>
                    <TableHead>IP Address</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {[...Array(5)].map((_, i) => (
                    <TableRow key={i}>
                      <TableCell><Skeleton className="h-4 w-28" /></TableCell>
                      <TableCell><Skeleton className="h-4 w-24" /></TableCell>
                      <TableCell><Skeleton className="h-4 w-20" /></TableCell>
                      <TableCell><Skeleton className="h-4 w-20" /></TableCell>
                      <TableCell><Skeleton className="h-4 w-20" /></TableCell>
                      <TableCell><Skeleton className="h-4 w-24" /></TableCell>
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
            <h1 className="text-3xl font-bold tracking-tight">Audit Log</h1>
            <p className="text-muted-foreground">Review administrative and system actions</p>
          </div>
        </div>
        <Card>
          <CardContent className="text-center py-8">
            <AlertCircle className="mx-auto h-12 w-12 text-destructive" />
            <h2 className="mt-4 text-xl font-semibold">Failed to load audit log</h2>
            <p className="mt-2 text-muted-foreground">{error.message || 'Unknown error'}</p>
            <Button className="mt-4" onClick={() => refetch()}>Retry</Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  const auditData = auditResponse as AuditListResponse

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Audit Log</h1>
          <p className="text-muted-foreground">Review administrative and system actions</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={downloadAudit}>
            <Download className="mr-2 h-4 w-4" />
            Export
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader>
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            <CardTitle>Audit Entries ({auditResponse?.total ?? 0})</CardTitle>
            <div className="flex flex-wrap items-center gap-2">
              <div className="relative w-64">
                <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input placeholder="Search audit log..." value={search} onChange={(e) => setSearch(e.target.value)} className="pl-10" />
              </div>
              <Select value={actionFilter} onValueChange={setActionFilter}>
                <SelectTrigger className="w-40">
                  <SelectValue placeholder="All Actions" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Actions</SelectItem>
                  <SelectItem value="alert.">Alert Actions</SelectItem>
                  <SelectItem value="rule.">Rule Actions</SelectItem>
                  <SelectItem value="agent.">Agent Actions</SelectItem>
                  <SelectItem value="auth.">Auth Actions</SelectItem>
                  <SelectItem value="config.">Config Actions</SelectItem>
                </SelectContent>
              </Select>
              <Select value={resultFilter} onValueChange={setResultFilter}>
                <SelectTrigger className="w-36">
                  <SelectValue placeholder="All Results" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Results</SelectItem>
                  <SelectItem value="success">Success</SelectItem>
                  <SelectItem value="failure">Failure</SelectItem>
                  <SelectItem value="denied">Denied</SelectItem>
                </SelectContent>
              </Select>
              <Select value={actorTypeFilter} onValueChange={setActorTypeFilter}>
                <SelectTrigger className="w-36">
                  <SelectValue placeholder="All Actors" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Actors</SelectItem>
                  <SelectItem value="user">User</SelectItem>
                  <SelectItem value="agent">Agent</SelectItem>
                  <SelectItem value="system">System</SelectItem>
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
                  <TableHead>Timestamp</TableHead>
                  <TableHead>Actor</TableHead>
                  <TableHead>Action</TableHead>
                  <TableHead>Resource</TableHead>
                  <TableHead>Result</TableHead>
                  <TableHead>IP Address</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {auditData.data?.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={6} className="text-center py-8 text-muted-foreground">No audit entries found</TableCell>
                  </TableRow>
                ) : (
                  auditData.data?.map((log) => (
                    <TableRow key={log.id}>
                      <TableCell className="font-mono text-sm">{formatDate(log.timestamp)}</TableCell>
                      <TableCell className="font-medium">{log.actor_name || log.actor_id}</TableCell>
                      <TableCell>
                        <code className="text-xs">{log.action}</code>
                      </TableCell>
                      <TableCell>
                        <code className="text-xs text-muted-foreground">{log.resource_id || log.resource_type || '—'}</code>
                      </TableCell>
                      <TableCell>{getResultBadge(log.result)}</TableCell>
                      <TableCell>{log.ip_address || '—'}</TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>
          <div className="flex items-center justify-between mt-4">
            <p className="text-sm text-muted-foreground">
              Showing {(page - 1) * pageSize + 1} to {Math.min(page * pageSize, auditData.total || 0)} of {auditData.total || 0} results
            </p>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1 || isLoading}>
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <Button variant="outline" size="sm" onClick={() => setPage(p => p + 1)} disabled={page >= (auditData.total_pages || 1) || isLoading}>
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

export default AuditPage
