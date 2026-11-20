import { useState, useMemo } from 'react'
import { Cpu, Search, Filter, ChevronLeft, ChevronRight, FilterX, Download, Eye, ChevronDown, ChevronUp, Globe, Hash, Shield, MoreHorizontal, GitBranch, X, Server, Network, FileText, Database } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
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
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger, DropdownMenuSeparator } from '@components/ui/dropdown-menu'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@components/ui/select'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@components/ui/tabs'
import { ScrollArea } from '@components/ui/scroll-area'
import { Label } from '@components/ui/label'
import { Skeleton } from '@components/ui/skeleton'
import { Separator } from '@components/ui/separator'
import { cn } from '@lib/utils'
import api from '@lib/api'
import { formatDate, formatRelativeTime } from '@lib/utils'

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
  num_threads: number | null
  num_handles: number | null
  memory_rss_mb: number | null
  connections: Array<{
    local_address: string
    remote_address: string
    status: string
    family: string
    type: string
    protocol?: string
  }> | null
  exe_sha256: string | null
  integrity_level: string | null
  status?: string
}

interface ProcessListResponse {
  data: ProcessTelemetry[]
  total: number
  page: number
  page_size: number
  total_pages: number
  snapshot_at?: string | null
  is_stale?: boolean
  reporting_agents?: number
  stale_agents?: number
}

interface ProcessDetailResponse {
  process: ProcessTelemetry
  process_tree: Array<{
    pid: number
    ppid: number
    name: string
    cmdline: string
    username: string
    exe: string
    children: number[]
  }>
  network_connections: Array<{
    local_address: string
    remote_address: string
    status: string
    protocol: string
  }>
  file_hashes: Record<string, string>
  signature_info: {
    is_signed: boolean
    signer_name: string
    issuer_name: string
    timestamp: string
    is_trusted: boolean
  }
  parent_process: {
    pid: number
    name: string
    cmdline: string
    exe: string
    username: string
  } | null
  child_processes: Array<{
    pid: number
    name: string
    cmdline: string
    exe: string
    username: string
  }>
}

export function ProcessExplorerPage() {
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(50)
  const [sort, setSort] = useState<string>('collected_at')
  const [order, setOrder] = useState<'asc' | 'desc'>('desc')
  const [selectedProcess, setSelectedProcess] = useState<ProcessTelemetry | null>(null)
  const [detailView, setDetailView] = useState<string>('details')
  const [filters, setFilters] = useState({
    agent_id: '',
    name: '',
    username: '',
    status: '',
  })

  const { data: processesResponse, isLoading, error } = useQuery<ProcessListResponse>({
    queryKey: ['processes', 'list', page, pageSize, sort, order, filters],
    queryFn: async () => {
      const params = new URLSearchParams({
        page: page.toString(),
        limit: pageSize.toString(),
        sort,
        order,
        ...(filters.agent_id && { agent_id: filters.agent_id }),
        ...(filters.name && { name: filters.name }),
        ...(filters.username && { username: filters.username }),
        ...(filters.status && { status: filters.status }),
      })
      const response = await api.get<ProcessListResponse>(`/api/v1/telemetry/processes?${params.toString()}`)
      return response.data
    },
    placeholderData: { data: [], total: 0, page: 1, page_size: 50, total_pages: 1 },
    refetchInterval: 60_000,
  })

  const { data: processDetail, isLoading: detailLoading } = useQuery<ProcessDetailResponse>({
    queryKey: ['process', 'detail', selectedProcess?.id],
    queryFn: async () => {
      const response = await api.get(`/api/v1/telemetry/processes/${selectedProcess?.id}`)
      return response.data
    },
    enabled: !!selectedProcess,
    refetchInterval: 60_000,
  })

  const filteredProcesses = useMemo(() => {
    let filtered = processesResponse?.data || []
    if (filters.name) {
      filtered = filtered.filter(p => p.name.toLowerCase().includes(filters.name!.toLowerCase()))
    }
    if (filters.username) {
      filtered = filtered.filter(p => p.username?.toLowerCase().includes(filters.username!.toLowerCase()))
    }
    return filtered
  }, [processesResponse?.data, filters])

  const handleSort = (column: typeof sort) => {
    if (sort === column) {
      setOrder(order === 'asc' ? 'desc' : 'asc')
    } else {
      setSort(column)
      setOrder('asc')
    }
  }

  const clearFilters = () => {
    setFilters({ agent_id: '', name: '', username: '', status: '' })
  }

  const handleRowClick = (process: ProcessTelemetry) => {
    setSelectedProcess(process)
    setDetailView('details')
  }

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'RUNNING':
        return <Badge className="badge-success">Running</Badge>
      case 'STOPPED':
        return <Badge className="badge-offline">Stopped</Badge>
      case 'PAUSED':
        return <Badge className="badge-stale">Paused</Badge>
      default:
        return <Badge>{status}</Badge>
    }
  }

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">Process Explorer</h1>
            <p className="text-muted-foreground">Search and analyze running processes across endpoints</p>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => setSelectedProcess(null)}>
              <X className="mr-2 h-4 w-4" />
              Clear Selection
            </Button>
            <Button variant="outline" size="sm" onClick={() => window.open('/api/v1/telemetry/processes/export', '_blank')}>
              <Download className="mr-2 h-4 w-4" />
              Export CSV
            </Button>
          </div>
        </div>
        <Card className="mb-4">
          <CardContent className="pt-4">
            <Skeleton className="h-10 w-full" />
          </CardContent>
        </Card>
        <Card>
          <CardContent>
            <div className="table-container">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>PID</TableHead>
                    <TableHead>Name</TableHead>
                    <TableHead>CPU %</TableHead>
                    <TableHead>Memory %</TableHead>
                    <TableHead>User</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="w-48">Command Line</TableHead>
                    <TableHead className="w-32">Actions</TableHead>
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
                      <TableCell><Skeleton className="h-4 w-16" /></TableCell>
                      <TableCell><Skeleton className="h-4 w-48" /></TableCell>
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
            <h1 className="text-3xl font-bold tracking-tight">Process Explorer</h1>
            <p className="text-muted-foreground">Search and analyze running processes across endpoints</p>
          </div>
        </div>
        <Card>
          <CardContent className="text-center py-8">
            <Cpu className="mx-auto h-12 w-12 text-destructive" />
            <h2 className="mt-4 text-xl font-semibold">Failed to load processes</h2>
            <p className="mt-2 text-muted-foreground">{error.message || 'Unknown error'}</p>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Process Explorer</h1>
          <p className="text-muted-foreground">Search and analyze running processes across endpoints</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => setSelectedProcess(null)}>
            <X className="mr-2 h-4 w-4" />
            Clear Selection
          </Button>
          <Button variant="outline" size="sm" onClick={() => window.open('/api/v1/telemetry/processes/export', '_blank')}>
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
              <Select value={filters.status} onValueChange={(v) => setFilters({ ...filters, status: v })}>
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="All Status" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="">All Status</SelectItem>
                  <SelectItem value="RUNNING">Running</SelectItem>
                  <SelectItem value="STOPPED">Stopped</SelectItem>
                  <SelectItem value="PAUSED">Paused</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <Button variant="outline" size="sm" onClick={clearFilters}>
              <FilterX className="mr-2 h-4 w-4" />
              Clear Filters
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            <CardTitle>Processes ({processesResponse?.total || 0})</CardTitle>
            <div className="flex items-center gap-2">
              <div className="relative w-64">
                <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  placeholder="Search processes..."
                  value={filters.name}
                  onChange={(e) => setFilters({ ...filters, name: e.target.value })}
                  className="pl-10"
                />
              </div>
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
                {order === 'asc' ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {(processesResponse?.is_stale || (processesResponse?.stale_agents ?? 0) > 0) && <div className="mb-4 rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm">
            {processesResponse?.is_stale
              ? 'No recent process telemetry is available.'
              : `${processesResponse?.stale_agents} endpoint${processesResponse?.stale_agents === 1 ? '' : 's'} have stale process telemetry.`} Start or reconnect the SentinelWatch agent, then wait for its next collection and upload.
          </div>}
          <div className="table-container">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead onClick={() => handleSort('pid')} className="cursor-pointer select-none">PID</TableHead>
                  <TableHead onClick={() => handleSort('name')} className="cursor-pointer select-none">Name</TableHead>
                  <TableHead onClick={() => handleSort('cpu_percent')} className="cursor-pointer select-none">CPU %</TableHead>
                  <TableHead onClick={() => handleSort('memory_percent')} className="cursor-pointer select-none">Memory %</TableHead>
                  <TableHead>User</TableHead>
                  <TableHead>Threads</TableHead>
                  <TableHead>Handles</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="w-48">Command Line</TableHead>
                  <TableHead className="w-32">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredProcesses.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={10} className="text-center py-8 text-muted-foreground">
                      {processesResponse?.is_stale ? 'Process data is stale or unavailable.' : 'No processes match the current filters.'}
                    </TableCell>
                  </TableRow>
                )}
                {filteredProcesses.map((proc) => (
                  <TableRow
                    key={proc.id}
                    className={cn(
                      'cursor-pointer transition-colors hover:bg-muted/50',
                      selectedProcess?.id === proc.id && 'bg-primary/10'
                    )}
                    onClick={() => handleRowClick(proc)}
                  >
                    <TableCell className="font-mono">{proc.pid}</TableCell>
                    <TableCell className="font-medium">{proc.name}</TableCell>
                    <TableCell>{proc.cpu_percent?.toFixed(1) || '0'}%</TableCell>
                    <TableCell>{proc.memory_percent?.toFixed(1) || '0'}%</TableCell>
                    <TableCell>{proc.username || 'N/A'}</TableCell>
                    <TableCell>{proc.num_threads ?? '—'}</TableCell>
                    <TableCell>{proc.num_handles ?? '—'}</TableCell>
                    <TableCell>{getStatusBadge(proc.status || 'UNKNOWN')}</TableCell>
                    <TableCell>
                      <code className="text-xs text-muted-foreground max-w-[300px] truncate block">{proc.cmdline || 'N/A'}</code>
                    </TableCell>
                    <TableCell>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon" className="h-8 w-8">
                            <MoreHorizontal className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem onClick={() => { setSelectedProcess(proc); setDetailView('details'); }}>
                            <Eye className="mr-2 h-4 w-4" />
                            View Details
                          </DropdownMenuItem>
                          <DropdownMenuItem onClick={() => { setSelectedProcess(proc); setDetailView('tree'); }}>
                            <GitBranch className="mr-2 h-4 w-4" />
                            Process Tree
                          </DropdownMenuItem>
                          <DropdownMenuItem onClick={() => { setSelectedProcess(proc); setDetailView('network'); }}>
                            <Globe className="mr-2 h-4 w-4" />
                            Network Connections
                          </DropdownMenuItem>
                          <DropdownMenuItem onClick={() => { setSelectedProcess(proc); setDetailView('hashes'); }}>
                            <Hash className="mr-2 h-4 w-4" />
                            File Hashes
                          </DropdownMenuItem>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem onClick={() => { setSelectedProcess(proc); setDetailView('signature'); }}>
                            <Shield className="mr-2 h-4 w-4" />
                            Signature Info
                          </DropdownMenuItem>
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
              Showing {(processesResponse?.total || 0) === 0 ? 0 : (page - 1) * pageSize + 1} to {Math.min(page * pageSize, processesResponse?.total || 0)} of {processesResponse?.total || 0} results
            </p>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}>
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <Button variant="outline" size="sm" onClick={() => setPage(p => p + 1)} disabled={page >= (processesResponse?.total_pages || 1)}>
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {selectedProcess && (
        <div className="fixed inset-0 z-50 bg-background/95 backdrop-blur-sm" onClick={() => setSelectedProcess(null)}>
          <div className="max-w-4xl mx-auto my-8 bg-card rounded-lg shadow-xl max-h-[90vh] overflow-hidden flex flex-col">
            <div className="flex items-center justify-between p-4 border-b">
              <div>
                <h2 className="text-xl font-bold">{selectedProcess.name}</h2>
                <p className="text-sm text-muted-foreground">PID: {selectedProcess.pid} | PPID: {selectedProcess.ppid}</p>
              </div>
              <Button variant="ghost" size="icon" onClick={() => setSelectedProcess(null)}>
                <X className="h-5 w-5" />
              </Button>
            </div>
            <Tabs value={detailView} onValueChange={setDetailView} className="border-b">
              <TabsList className="grid w-full grid-cols-6">
                <TabsTrigger value="details">Details</TabsTrigger>
                <TabsTrigger value="tree">Process Tree</TabsTrigger>
                <TabsTrigger value="network">Network</TabsTrigger>
                <TabsTrigger value="hashes">Hashes</TabsTrigger>
                <TabsTrigger value="signature">Signature</TabsTrigger>
              </TabsList>

              <TabsContent value="details" className="p-4 overflow-auto flex-1">
                <div className="grid gap-4 md:grid-cols-2">
                  <div className="space-y-3">
                    <div>
                      <Label>Process Name</Label>
                      <p className="font-medium">{selectedProcess.name}</p>
                    </div>
                    <div>
                      <Label>PID</Label>
                      <p className="font-mono">{selectedProcess.pid}</p>
                    </div>
                    <div>
                      <Label>Parent PID</Label>
                      <p className="font-mono">{selectedProcess.ppid}</p>
                    </div>
                    <div>
                      <Label>Executable Path</Label>
                      <p className="font-mono text-sm truncate">{selectedProcess.exe || 'N/A'}</p>
                    </div>
                    <div>
                      <Label>Command Line</Label>
                      <p className="font-mono text-xs text-muted-foreground break-all">{selectedProcess.cmdline || 'N/A'}</p>
                    </div>
                    <div>
                      <Label>User</Label>
                      <p>{selectedProcess.username || 'N/A'}</p>
                    </div>
                    <div>
                      <Label>Start Time</Label>
                      <p>{selectedProcess.create_time ? formatDate(selectedProcess.create_time) : 'N/A'}</p>
                    </div>
                    <div>
                      <Label>Observed At</Label>
                      <p>{selectedProcess.observed_at ? formatDate(selectedProcess.observed_at) : 'N/A'}</p>
                    </div>
                    <div>
                      <Label>Terminated At</Label>
                      <p>{selectedProcess.terminated_at ? formatDate(selectedProcess.terminated_at) : 'N/A'}</p>
                    </div>
                    <div>
                      <Label>Ingested At</Label>
                      <p>{selectedProcess.ingested_at ? formatDate(selectedProcess.ingested_at) : 'N/A'}</p>
                    </div>
                    <div>
                      <Label>CPU Usage</Label>
                      <p>{selectedProcess.cpu_percent?.toFixed(1) || '0'}%</p>
                    </div>
                    <div>
                      <Label>Memory</Label>
                      <p>{selectedProcess.memory_rss_mb?.toFixed(1) || '0'} MB ({selectedProcess.memory_percent?.toFixed(1) || '0'}%)</p>
                    </div>
                    <div>
                      <Label>Integrity Level</Label>
                      <p>{selectedProcess.integrity_level || 'Unknown'}</p>
                    </div>
                  </div>
                  <div className="space-y-3">
                    <div>
                      <Label>Command Line</Label>
                      <pre className="text-xs text-muted-foreground bg-muted p-3 rounded overflow-auto max-h-40">{selectedProcess.cmdline || 'N/A'}</pre>
                    </div>
                    {selectedProcess.connections && selectedProcess.connections.length > 0 && (
                      <div>
                        <Label>Network Connections</Label>
                        <Table>
                          <TableHeader>
                            <TableRow>
                              <TableHead>Local</TableHead>
                              <TableHead>Remote</TableHead>
                              <TableHead>Status</TableHead>
                              <TableHead>Protocol</TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {selectedProcess.connections.map((conn, i) => (
                              <TableRow key={i}>
                                <TableCell className="font-mono text-xs">{conn.local_address}</TableCell>
                                <TableCell className="font-mono text-xs">{conn.remote_address}</TableCell>
                                <TableCell><Badge variant="outline">{conn.status}</Badge></TableCell>
                                <TableCell>{conn.protocol}</TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      </div>
                    )}
                  </div>
                </div>
              </TabsContent>

              <TabsContent value="tree" className="p-4 overflow-auto flex-1">
                {detailLoading ? (
                  <div className="flex items-center justify-center h-64">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
                  </div>
                ) : (
                  <ScrollArea className="h-[400px]">
                    <pre className="text-xs font-mono whitespace-pre-wrap">{JSON.stringify(processDetail?.process_tree || [], null, 2)}</pre>
                  </ScrollArea>
                )}
              </TabsContent>

              <TabsContent value="network" className="p-4 overflow-auto flex-1">
                {detailLoading ? (
                  <div className="flex items-center justify-center h-64">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
                  </div>
                ) : processDetail?.network_connections && processDetail.network_connections.length > 0 ? (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Local</TableHead>
                        <TableHead>Remote</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead>Protocol</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {processDetail.network_connections.map((conn, i) => (
                        <TableRow key={i}>
                          <TableCell className="font-mono text-xs">{conn.local_address}</TableCell>
                          <TableCell className="font-mono text-xs">{conn.remote_address}</TableCell>
                          <TableCell><Badge variant="outline">{conn.status}</Badge></TableCell>
                          <TableCell>{conn.protocol}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                ) : (
                  <p className="text-muted-foreground text-center py-8">No network connection data available</p>
                )}
              </TabsContent>

              <TabsContent value="hashes" className="p-4 overflow-auto flex-1">
                {detailLoading ? (
                  <div className="flex items-center justify-center h-64">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
                  </div>
                ) : processDetail?.file_hashes && Object.keys(processDetail.file_hashes).length > 0 ? (
                  <div className="grid gap-2 md:grid-cols-2">
                    {Object.entries(processDetail.file_hashes).map(([algo, hash]) => (
                      <div key={algo} className="flex items-center gap-3 p-3 bg-muted/50 rounded-lg">
                        <Badge variant="outline" className="font-mono text-xs">{algo.toUpperCase()}</Badge>
                        <code className="font-mono text-xs text-muted-foreground flex-1 break-all">{hash}</code>
                        <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => navigator.clipboard.writeText(hash)}>
                          <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3" /></svg>
                        </Button>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-muted-foreground text-center py-8">No file hashes available</p>
                )}
              </TabsContent>

              <TabsContent value="signature" className="p-4 overflow-auto flex-1">
                {detailLoading ? (
                  <div className="flex items-center justify-center h-64">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
                  </div>
                ) : (
                  <div className="grid gap-4 md:grid-cols-2">
                    <div className="space-y-2">
                      <Label>Signed</Label>
                      <Badge className={processDetail?.signature_info?.is_signed ? 'badge-success' : 'badge-destructive'}>
                        {processDetail?.signature_info?.is_signed ? 'Yes' : 'No'}
                      </Badge>
                    </div>
                    <div className="space-y-2">
                      <Label>Trusted</Label>
                      <Badge className={processDetail?.signature_info?.is_trusted ? 'badge-success' : 'badge-destructive'}>
                        {processDetail?.signature_info?.is_trusted ? 'Yes' : 'No'}
                      </Badge>
                    </div>
                    <div className="space-y-2">
                      <Label>Signer</Label>
                      <p className="text-sm">{processDetail?.signature_info?.signer_name || 'N/A'}</p>
                    </div>
                    <div className="space-y-2">
                      <Label>Issuer</Label>
                      <p className="text-sm">{processDetail?.signature_info?.issuer_name || 'N/A'}</p>
                    </div>
                    <div className="space-y-2">
                      <Label>Timestamp</Label>
                      <p className="text-sm">{processDetail?.signature_info?.timestamp ? formatDate(processDetail.signature_info.timestamp) : 'N/A'}</p>
                    </div>
                  </div>
                )}
              </TabsContent>
            </Tabs>
          </div>
        </div>
      )}
    </div>
  )
}

export default ProcessExplorerPage
