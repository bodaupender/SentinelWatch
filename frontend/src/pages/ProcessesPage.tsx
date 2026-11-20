import { useState } from 'react'
import { Search, Filter, ChevronLeft, ChevronRight, Cpu, HardDrive, Download } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@components/ui/table'
import { Input } from '@components/ui/input'
import { Button } from '@components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@components/ui/select'
import { Skeleton } from '@components/ui/skeleton'
import { cn } from '@lib/utils'
import api from '@lib/api'
import { formatRelativeTime } from '@lib/utils'

interface ProcessTelemetry {
  id: string
  agent_id: string
  agent_hostname: string | null
  collected_at: string
  observed_at: string | null
  terminated_at: string | null
  ingested_at: string | null
  sequence: number
  pid: number
  ppid: number
  name: string
  cmdline: string | null
  exe: string | null
  username: string | null
  create_time: string | null
  cpu_percent: number | null
  memory_percent: number | null
  memory_rss_mb: number | null
  connections: any[] | null
  exe_sha256: string | null
  integrity_level: string | null
}

interface ProcessListResponse {
  data: ProcessTelemetry[]
  total: number
  page: number
  page_size: number
  total_pages: number
  snapshot_at?: string | null
  is_stale?: boolean
}

export function ProcessesPage() {
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(50)
  const [sort, setSort] = useState<string>('collected_at')
  const [order, setOrder] = useState<'asc' | 'desc'>('desc')
  const [filters, setFilters] = useState({
    agent_id: '',
    name: '',
    username: '',
  })

  const { data: processesResponse, isLoading, error, refetch } = useQuery<ProcessListResponse, Error>({
    queryKey: ['processes', 'list', page, pageSize, sort, order, filters, search],
    queryFn: async () => {
      const params = new URLSearchParams({
        page: page.toString(),
        limit: pageSize.toString(),
        sort,
        order,
        ...(filters.agent_id && { agent_id: filters.agent_id }),
        ...(filters.name && { name: filters.name }),
        ...(filters.username && { username: filters.username }),
        ...(search && { search }),
      })
      const response = await api.get<ProcessListResponse>(`/api/v1/telemetry/processes?${params.toString()}`)
      return response.data
    },
    placeholderData: { data: [], total: 0, page: 1, page_size: 50, total_pages: 1 },
    refetchInterval: 60_000,
  })
  const { data: agentResponse } = useQuery<{ data: { id: string; hostname: string; status: string }[] }>({
    queryKey: ['agents', 'process-filter'],
    queryFn: async () => (await api.get('/api/v1/agents?limit=100')).data,
  })

  const filteredProcesses = processesResponse?.data ?? []

  const handleSort = (column: typeof sort) => {
    if (sort === column) {
      setOrder(order === 'asc' ? 'desc' : 'asc')
    } else {
      setSort(column)
      setOrder('asc')
    }
  }

  const clearFilters = () => {
    setFilters({ agent_id: '', name: '', username: '' })
    setSearch('')
  }

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">Processes</h1>
            <p className="text-muted-foreground">Search and analyze running processes across endpoints</p>
          </div>
        </div>
        <Card>
          <CardHeader>
            <CardTitle>Processes (loading...)</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="table-container">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>PID</TableHead>
                    <TableHead>Name</TableHead>
                    <TableHead>CPU</TableHead>
                    <TableHead>Memory</TableHead>
                    <TableHead>User</TableHead>
                    <TableHead>Command Line</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {[...Array(5)].map((_, i) => (
                    <TableRow key={i}>
                      <TableCell><Skeleton className="h-4 w-16" /></TableCell>
                      <TableCell><Skeleton className="h-4 w-24" /></TableCell>
                      <TableCell><Skeleton className="h-4 w-16" /></TableCell>
                      <TableCell><Skeleton className="h-4 w-20" /></TableCell>
                      <TableCell><Skeleton className="h-4 w-24" /></TableCell>
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
            <h1 className="text-3xl font-bold tracking-tight">Processes</h1>
            <p className="text-muted-foreground">Search and analyze running processes across endpoints</p>
          </div>
        </div>
        <Card>
          <CardContent className="text-center py-8">
            <Cpu className="mx-auto h-12 w-12 text-destructive" />
            <h2 className="mt-4 text-xl font-semibold">Failed to load processes</h2>
            <p className="mt-2 text-muted-foreground">{error.message || 'Unknown error'}</p>
            <Button className="mt-4" onClick={() => refetch()}>Retry</Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Processes</h1>
          <p className="text-muted-foreground">Search and analyze running processes across endpoints</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={async () => {
            const response = await api.get('/api/v1/telemetry/processes/export', { responseType: 'blob' })
            const url = URL.createObjectURL(response.data)
            const link = document.createElement('a')
            link.href = url
            link.download = 'sentinelwatch-processes.csv'
            link.click()
            URL.revokeObjectURL(url)
          }}>
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
                placeholder="Search processes..."
                value={filters.name}
                onChange={(e) => setFilters({ ...filters, name: e.target.value })}
                className="pl-10"
              />
            </div>
            <div className="relative w-64">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                placeholder="Filter by user..."
                value={filters.username}
                onChange={(e) => setFilters({ ...filters, username: e.target.value })}
                className="pl-10"
              />
            </div>
            <div className="relative w-48">
              <Select value={filters.agent_id || 'all'} onValueChange={(v) => setFilters({ ...filters, agent_id: v === 'all' ? '' : v })}>
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="All Agents" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Agents</SelectItem>
                  {(agentResponse?.data ?? []).map((agent) => <SelectItem key={agent.id} value={agent.id}>{agent.hostname} ({agent.status})</SelectItem>)}
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
            <div><CardTitle>Current Processes ({processesResponse?.total ?? 0})</CardTitle><p className="mt-1 text-xs text-muted-foreground">Distinct process IDs from the latest collected snapshot{processesResponse?.snapshot_at ? ` · ${formatRelativeTime(processesResponse.snapshot_at)}` : ''}</p></div>
            <div className="flex items-center gap-2">
              <Select value={sort} onValueChange={setSort}>
                <SelectTrigger className="w-40">
                  <SelectValue placeholder="Sort by" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="collected_at">Collection Time</SelectItem>
                  <SelectItem value="pid">PID</SelectItem>
                  <SelectItem value="name">Process Name</SelectItem>
                  <SelectItem value="cpu_percent">CPU %</SelectItem>
                  <SelectItem value="memory_percent">Memory %</SelectItem>
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
          {processesResponse?.is_stale && <div className="mb-4 rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm">This endpoint’s latest process snapshot is stale. Start or reconnect its SentinelWatch agent to refresh current process data.</div>}
          <div className="table-container">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead onClick={() => handleSort('pid')} className="cursor-pointer select-none">PID</TableHead>
                  <TableHead onClick={() => handleSort('name')} className="cursor-pointer select-none">Name</TableHead>
                  <TableHead onClick={() => handleSort('cpu_percent')} className="cursor-pointer select-none">CPU %</TableHead>
                  <TableHead onClick={() => handleSort('memory_percent')} className="cursor-pointer select-none">Memory %</TableHead>
                  <TableHead>User</TableHead>
                  <TableHead className="w-64">Command Line</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredProcesses.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={6} className="text-center py-8 text-muted-foreground">No processes found</TableCell>
                  </TableRow>
                ) : (
                  filteredProcesses.map((proc) => (
                    <TableRow key={proc.id}>
                      <TableCell className="font-mono">{proc.pid}</TableCell>
                      <TableCell className="font-medium">{proc.name}</TableCell>
                      <TableCell>{proc.cpu_percent?.toFixed(1) ?? '0'}%</TableCell>
                      <TableCell>{proc.memory_percent?.toFixed(1) ?? '0'}%</TableCell>
                      <TableCell>{proc.username ?? 'N/A'}</TableCell>
                      <TableCell>
                        <code className="text-xs text-muted-foreground max-w-[400px] truncate block">{proc.cmdline ?? 'N/A'}</code>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>
          <div className="flex items-center justify-between mt-4">
            <p className="text-sm text-muted-foreground">
              Showing {(page - 1) * pageSize + 1} to {Math.min(page * pageSize, processesResponse?.total ?? 0)} of {processesResponse?.total ?? 0} results
            </p>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1 || isLoading}>
                <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" /></svg>
              </Button>
              <Button variant="outline" size="sm" onClick={() => setPage(p => p + 1)} disabled={page >= (processesResponse?.total_pages ?? 1) || isLoading}>
                <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" /></svg>
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

export default ProcessesPage
