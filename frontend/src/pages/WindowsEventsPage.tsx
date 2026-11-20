"use client"

import { useState } from 'react'
import { Search, FilterX, ChevronLeft, ChevronRight, AlertCircle } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@components/ui/table'
import { Input } from '@components/ui/input'
import { Badge } from '@components/ui/badge'
import { Button } from '@components/ui/button'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@components/ui/dropdown-menu'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@components/ui/select'
import { Skeleton } from '@components/ui/skeleton'
import api from '@lib/api'
import { formatDate } from '@lib/utils'

interface WindowsEvent {
  id: string
  agent_id: string
  agent_hostname: string | null
  collected_at: string
  sequence: number
  event_id: number
  record_id: number
  channel: string
  provider_name: string
  level: string
  event_timestamp: string
  computer: string
  user_sid: string
  user_name: string
  user_domain: string
  message: string
  raw_xml: string
  extracted: Record<string, any>
  process_id: number
  process_name: string
  process_command_line: string
  parent_process_id: number
  parent_process_name: string
  process_hash_sha256: string
}

interface EventListResponse {
  data: WindowsEvent[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export function WindowsEventsPage() {
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [pageSize] = useState(50)
  const [sort, setSort] = useState<'event_timestamp' | 'event_id' | 'channel' | 'level'>('event_timestamp')
  const [order, setOrder] = useState<'asc' | 'desc'>('desc')
  const [filters, setFilters] = useState({
    channel: '',
    event_id: '',
    level: '',
    agent_id: '',
  })

  const filterString = JSON.stringify(filters)

  const { data: eventsResponse, isLoading, error, refetch } = useQuery<EventListResponse, Error>({
    queryKey: ['windows-events', 'list', page.toString(), pageSize.toString(), sort, order, filterString, search],
    queryFn: async () => {
      const params = new URLSearchParams({
        page: page.toString(),
        limit: pageSize.toString(),
        sort,
        order,
        ...(filters.channel && { channel: filters.channel }),
        ...(filters.event_id && { event_id: filters.event_id }),
        ...(filters.level && { level: filters.level }),
        ...(filters.agent_id && { agent_id: filters.agent_id }),
        ...(search && { search }),
      })
      const response = await api.get<EventListResponse>(`/api/v1/telemetry/events?${params.toString()}`)
      return response.data
    },
    placeholderData: { data: [], total: 0, page: 1, page_size: 50, total_pages: 1 },
    refetchInterval: 60_000,
  })

  const filteredEvents = eventsResponse?.data || []

  const handleSort = (column: typeof sort) => {
    if (sort === column) {
      setOrder(order === 'asc' ? 'desc' : 'asc')
    } else {
      setSort(column)
      setOrder('asc')
    }
  }

  const clearFilters = () => {
    setFilters({ channel: '', event_id: '', level: '', agent_id: '' })
    setSearch('')
  }

  const getLevelBadge = (level: string) => {
    switch (level?.toLowerCase()) {
      case 'critical':
        return <Badge className="badge-critical">Critical</Badge>
      case 'error':
        return <Badge className="badge-destructive">Error</Badge>
      case 'warning':
        return <Badge className="badge-high">Warning</Badge>
      case 'information':
        return <Badge className="badge-info">Information</Badge>
      case 'verbose':
        return <Badge className="badge-secondary">Verbose</Badge>
      default:
        return <Badge variant="outline">{level}</Badge>
    }
  }

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">Windows Events</h1>
            <p className="text-muted-foreground">Search and analyze Windows Event Logs across endpoints</p>
          </div>
        </div>
        <Card>
          <CardHeader>
            <CardTitle>Windows Events (loading...)</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="table-container">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Timestamp</TableHead>
                    <TableHead>Channel</TableHead>
                    <TableHead>Event ID</TableHead>
                    <TableHead>Level</TableHead>
                    <TableHead>Source</TableHead>
                    <TableHead>Computer</TableHead>
                    <TableHead>Message</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {[...Array(5)].map((_, i) => (
                    <TableRow key={i}>
                      <TableCell><Skeleton className="h-4 w-28" /></TableCell>
                      <TableCell><Skeleton className="h-4 w-20" /></TableCell>
                      <TableCell><Skeleton className="h-4 w-16" /></TableCell>
                      <TableCell><Skeleton className="h-4 w-20" /></TableCell>
                      <TableCell><Skeleton className="h-4 w-24" /></TableCell>
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
            <h1 className="text-3xl font-bold tracking-tight">Windows Events</h1>
            <p className="text-muted-foreground">Search and analyze Windows Event Logs across endpoints</p>
          </div>
        </div>
        <Card>
          <CardContent className="text-center py-8">
            <AlertCircle className="mx-auto h-12 w-12 text-destructive" />
            <h2 className="mt-4 text-xl font-semibold">Failed to load events</h2>
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
          <h1 className="text-3xl font-bold tracking-tight">Windows Events</h1>
          <p className="text-muted-foreground">Search and analyze Windows Event Logs across endpoints</p>
        </div>
      </div>

      <Card>
        <CardHeader className="pb-4">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            <CardTitle>Windows Events ({eventsResponse?.total || 0})</CardTitle>
            <div className="flex flex-wrap items-center gap-2">
              <div className="relative w-64">
                <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  placeholder="Search events..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  className="pl-10"
                />
              </div>
              <div className="flex items-center gap-2">
                <Select value={filters.channel} onValueChange={(e) => setFilters({ ...filters, channel: e })}>
                  <SelectTrigger className="w-40">
                    <SelectValue placeholder="All Channels" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="">All Channels</SelectItem>
                    <SelectItem value="Security">Security</SelectItem>
                    <SelectItem value="System">System</SelectItem>
                    <SelectItem value="Application">Application</SelectItem>
                    <SelectItem value="Microsoft-Windows-Sysmon/Operational">Sysmon</SelectItem>
                    <SelectItem value="Microsoft-Windows-PowerShell/Operational">PowerShell</SelectItem>
                  </SelectContent>
                </Select>
                <Select value={filters.level} onValueChange={(e) => setFilters({ ...filters, level: e })}>
                  <SelectTrigger className="w-36">
                    <SelectValue placeholder="All Levels" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="">All Levels</SelectItem>
                    <SelectItem value="critical">Critical</SelectItem>
                    <SelectItem value="error">Error</SelectItem>
                    <SelectItem value="warning">Warning</SelectItem>
                    <SelectItem value="information">Information</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <Button variant="outline" size="sm" onClick={clearFilters}>
                <FilterX className="mr-2 h-4 w-4" />
                Clear Filters
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="table-container">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead onClick={() => handleSort('event_timestamp')} className="cursor-pointer select-none">Timestamp</TableHead>
                  <TableHead onClick={() => handleSort('channel')} className="cursor-pointer select-none">Channel</TableHead>
                  <TableHead onClick={() => handleSort('event_id')} className="cursor-pointer select-none">Event ID</TableHead>
                  <TableHead>Level</TableHead>
                  <TableHead>Source</TableHead>
                  <TableHead>Computer</TableHead>
                  <TableHead>Message</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredEvents.map((event) => (
                  <TableRow key={event.id}>
                    <TableCell className="font-mono text-sm">{formatDate(event.event_timestamp)}</TableCell>
                    <TableCell>
                      <Badge variant="outline" className="text-xs">{event.channel}</Badge>
                    </TableCell>
                    <TableCell className="font-mono text-sm">{event.event_id}</TableCell>
                    <TableCell>{getLevelBadge(event.level)}</TableCell>
                    <TableCell className="text-sm">{event.provider_name}</TableCell>
                    <TableCell>{event.computer}</TableCell>
                    <TableCell>
                      <code className="text-xs text-muted-foreground max-w-[300px] truncate block">{event.message}</code>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          <div className="flex items-center justify-between mt-4">
            <p className="text-sm text-muted-foreground">
              Showing {(page - 1) * 50 + 1} to {Math.min(page * 50, eventsResponse?.total || 0)} of {eventsResponse?.total || 0} results
            </p>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1 || isLoading}>
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <Button variant="outline" size="sm" onClick={() => setPage(p => p + 1)} disabled={page >= (eventsResponse?.total_pages || 1) || isLoading}>
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

function getLevelBadge(level: string) {
  switch (level?.toLowerCase()) {
    case 'critical':
      return <Badge className="badge-critical">Critical</Badge>
    case 'error':
      return <Badge className="badge-destructive">Error</Badge>
    case 'warning':
      return <Badge className="badge-high">Warning</Badge>
    case 'information':
      return <Badge className="badge-info">Information</Badge>
    case 'verbose':
      return <Badge className="badge-secondary">Verbose</Badge>
    default:
      return <Badge variant="outline">{level}</Badge>
  }
}

export default WindowsEventsPage
