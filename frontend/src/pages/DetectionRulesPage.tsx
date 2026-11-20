import { useState } from 'react'
import { Search, Filter, Plus, MoreHorizontal, Play, Pause, Edit, Trash2, Eye, ChevronLeft, ChevronRight, FileCode } from 'lucide-react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@components/ui/table'
import { Input } from '@components/ui/input'
import { Badge } from '@components/ui/badge'
import { Button } from '@components/ui/button'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger, DropdownMenuSeparator } from '@components/ui/dropdown-menu'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter, DialogTrigger } from '@components/ui/dialog'
import { Textarea } from '@components/ui/textarea'
import { Label } from '@components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@components/ui/select'
import { Skeleton } from '@components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@components/ui/tabs'
import { cn } from '@lib/utils'
import api from '@lib/api'
import { formatDate } from '@lib/utils'
import { toast } from 'sonner'

interface DetectionRule {
  id: string
  name: string
  display_name: string
  description: string | null
  rule_type: 'process' | 'service' | 'startup' | 'eventlog' | 'correlation'
  severity: 'critical' | 'high' | 'medium' | 'low' | 'info'
  status: 'active' | 'staging' | 'disabled' | 'draft' | 'deprecated'
  mitre_techniques: string[] | null
  mitre_tactics: string[] | null
  tags: string[] | null
  version: number
  condition: string
  condition_version: number
  previous_version_id: string | null
  promoted_from_staging_at: string | null
  promoted_by: string | null
  author: string | null
  owner: string | null
  created_at: string
  updated_at: string
}

interface RuleListResponse {
  data: DetectionRule[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

interface BuiltinRule {
  rule_id: string
  rule_name: string
  description: string
  category: string
  severity: string
  confidence: number
  condition: string
  mitre_techniques: string[]
  evidence_requirements: string[]
  investigation_guidance: string | null
  false_positive_rate: number
  enabled: boolean
  version: number
}

export function DetectionRulesPage() {
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(50)
  const [typeFilter, setTypeFilter] = useState('all')
  const [statusFilter, setStatusFilter] = useState('all')
  const [selectedRule, setSelectedRule] = useState<DetectionRule | BuiltinRule | null>(null)
  const [isTestOpen, setIsTestOpen] = useState(false)
  const [isEditOpen, setIsEditOpen] = useState(false)
  const [isCreateOpen, setIsCreateOpen] = useState(false)
  const [activeTab, setActiveTab] = useState<string>('custom')

  const queryClient = useQueryClient()

  const { data: rulesResponse, isLoading, error } = useQuery<RuleListResponse>({
    queryKey: ['rules', 'list', page, pageSize, typeFilter, statusFilter, search],
    queryFn: async () => {
      const params = new URLSearchParams({
        page: page.toString(),
        limit: pageSize.toString(),
        ...(typeFilter !== 'all' && { rule_type: typeFilter }),
        ...(statusFilter !== 'all' && { status: statusFilter }),
        ...(search && { search }),
      })
      const response = await api.get<RuleListResponse>(`/api/v1/rules?${params.toString()}`)
      return response.data
    },
    placeholderData: { data: [], total: 0, page: 1, page_size: 50, total_pages: 1 },
    refetchInterval: 60_000,
  })

  const { data: builtinRules, isLoading: builtinLoading } = useQuery<BuiltinRule[]>({
    queryKey: ['builtin-rules'],
    queryFn: async () => {
      const response = await api.get('/api/v1/rules/builtin')
      return response.data
    },
    refetchInterval: 60_000,
  })

  const testMutation = useMutation({
    mutationFn: async (ruleId: string) => {
      const response = await api.post(`/api/v1/rules/${ruleId}/test`, { telemetry: { evaluate_all: true } })
      return response.data
    },
    onSuccess: () => {
      toast.success('Rule test completed')
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Test failed')
    },
  })

  const promoteMutation = useMutation({
    mutationFn: async (ruleId: string) => {
      const response = await api.post(`/api/v1/rules/${ruleId}/promote`)
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rules'] })
      toast.success('Rule promoted to active')
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Promotion failed')
    },
  })

  const demoteMutation = useMutation({
    mutationFn: async (ruleId: string) => {
      const response = await api.post(`/api/v1/rules/${ruleId}/demote`)
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rules'] })
      toast.success('Rule demoted to staging')
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Demotion failed')
    },
  })

  const deleteMutation = useMutation({
    mutationFn: async (ruleId: string) => {
      const response = await api.delete(`/api/v1/rules/${ruleId}`)
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rules'] })
      toast.success('Rule deleted')
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Deletion failed')
    },
  })

  const createMutation = useMutation({
    mutationFn: async (data: any) => {
      const response = await api.post('/api/v1/rules', data)
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rules'] })
      toast.success('Rule created')
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Creation failed')
    },
  })

  const updateMutation = useMutation({
    mutationFn: async ({ id, data }: { id: string; data: any }) => {
      const response = await api.put(`/api/v1/rules/${id}`, data)
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rules'] })
      toast.success('Rule updated')
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Update failed')
    },
  })

  const filteredRules = rulesResponse?.data?.filter((rule) => {
    const matchesSearch = rule.display_name.toLowerCase().includes(search.toLowerCase()) ||
      rule.name.toLowerCase().includes(search.toLowerCase())
    const matchesType = typeFilter === 'all' || rule.rule_type === typeFilter
    const matchesStatus = statusFilter === 'all' || rule.status === statusFilter
    return matchesSearch && matchesType && matchesStatus
  })

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'active':
        return <Badge className="badge-success"><Play className="mr-1 h-3 w-3" /> Active</Badge>
      case 'staging':
        return <Badge className="badge-stale"><Pause className="mr-1 h-3 w-3" /> Staging</Badge>
      case 'disabled':
        return <Badge className="badge-offline">Disabled</Badge>
      case 'draft':
        return <Badge className="badge-info">Draft</Badge>
      default:
        return <Badge>{status}</Badge>
    }
  }

  const getTypeBadge = (type: string) => {
    const colors = {
      process: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 text-blue-300',
      service: 'bg-green-100 text-green-800 dark:bg-green-900/30 text-green-300',
      startup: 'bg-purple-100 text-purple-800 dark:bg-purple-900/30 text-purple-300',
      eventlog: 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 text-orange-300',
      correlation: 'bg-red-100 text-red-800 dark:bg-red-900/30 text-red-300',
    }
    return <Badge className={colors[type as keyof typeof colors] || 'badge-info'}>{type}</Badge>
  }

  const getSeverityBadge = (severity: string) => {
    const colors = {
      critical: 'badge-critical',
      high: 'badge-high',
      medium: 'badge-medium',
      low: 'badge-low',
      info: 'badge-info',
    }
    return <Badge className={colors[severity as keyof typeof colors] || 'badge-info'}>{severity}</Badge>
  }

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">Detection Rules</h1>
            <p className="text-muted-foreground">Manage and test detection rules</p>
          </div>
          <Button onClick={() => setIsCreateOpen(true)}>
            <Plus className="mr-2 h-4 w-4" />
            Create Rule
          </Button>
        </div>
        <Card>
          <CardHeader>
            <CardTitle>Detection Rules (loading...)</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="table-container">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Name</TableHead>
                    <TableHead>Display Name</TableHead>
                    <TableHead>Type</TableHead>
                    <TableHead>Severity</TableHead>
                    <TableHead>MITRE</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {[...Array(5)].map((_, i) => (
                    <TableRow key={i}>
                      <TableCell><Skeleton className="h-4 w-24" /></TableCell>
                      <TableCell><Skeleton className="h-4 w-32" /></TableCell>
                      <TableCell><Skeleton className="h-4 w-20" /></TableCell>
                      <TableCell><Skeleton className="h-4 w-20" /></TableCell>
                      <TableCell><Skeleton className="h-4 w-24" /></TableCell>
                      <TableCell><Skeleton className="h-4 w-20" /></TableCell>
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
            <h1 className="text-3xl font-bold tracking-tight">Detection Rules</h1>
            <p className="text-muted-foreground">Manage and test detection rules</p>
          </div>
        </div>
        <Card>
          <CardContent className="text-center py-8">
            <FileCode className="mx-auto h-12 w-12 text-destructive" />
            <h2 className="mt-4 text-xl font-semibold">Failed to load rules</h2>
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
          <h1 className="text-3xl font-bold tracking-tight">Detection Rules</h1>
          <p className="text-muted-foreground">Manage and test detection rules</p>
        </div>
        <Button onClick={() => setIsCreateOpen(true)}>
          <Plus className="mr-2 h-4 w-4" />
          Create Rule
        </Button>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
        <TabsList className="grid w-full grid-cols-2">
          <TabsTrigger value="custom">Custom Rules</TabsTrigger>
          <TabsTrigger value="builtin">Built-in Rules</TabsTrigger>
        </TabsList>

        <TabsContent value="custom" className="space-y-4">
          <Card>
            <CardHeader>
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                <CardTitle>Custom Rules ({rulesResponse?.data?.length || 0})</CardTitle>
                <div className="flex flex-wrap items-center gap-2">
                  <div className="relative w-64">
                    <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                    <Input placeholder="Search rules..." value={search} onChange={(e) => setSearch(e.target.value)} className="pl-10" />
                  </div>
                  <Select value={typeFilter} onValueChange={setTypeFilter}>
                    <SelectTrigger className="w-36">
                      <SelectValue placeholder="All Types" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All Types</SelectItem>
                      <SelectItem value="process">Process</SelectItem>
                      <SelectItem value="service">Service</SelectItem>
                      <SelectItem value="startup">Startup</SelectItem>
                      <SelectItem value="eventlog">Event Log</SelectItem>
                      <SelectItem value="correlation">Correlation</SelectItem>
                    </SelectContent>
                  </Select>
                  <Select value={statusFilter} onValueChange={setStatusFilter}>
                    <SelectTrigger className="w-36">
                      <SelectValue placeholder="All Status" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All Status</SelectItem>
                      <SelectItem value="active">Active</SelectItem>
                      <SelectItem value="staging">Staging</SelectItem>
                      <SelectItem value="disabled">Disabled</SelectItem>
                      <SelectItem value="draft">Draft</SelectItem>
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
                      <TableHead>Name</TableHead>
                      <TableHead>Display Name</TableHead>
                      <TableHead>Type</TableHead>
                      <TableHead>Severity</TableHead>
                      <TableHead>MITRE</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead className="text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {filteredRules?.map((rule) => (
                      <TableRow key={rule.id}>
                        <TableCell className="font-mono text-sm">{rule.name}</TableCell>
                        <TableCell className="font-medium">{rule.display_name}</TableCell>
                        <TableCell>{getTypeBadge(rule.rule_type)}</TableCell>
                        <TableCell>{getSeverityBadge(rule.severity)}</TableCell>
                        <TableCell><code className="text-xs text-muted-foreground">{rule.mitre_techniques?.join(', ') || '—'}</code></TableCell>
                        <TableCell>{getStatusBadge(rule.status)}</TableCell>
                        <TableCell className="text-right">
                          <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                              <Button variant="ghost" size="icon" className="h-8 w-8">
                                <MoreHorizontal className="h-4 w-4" />
                              </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end">
                              <DropdownMenuItem onClick={() => { setSelectedRule(rule); setIsTestOpen(true); }}>
                                <Eye className="mr-2 h-4 w-4" />
                                Test Rule
                              </DropdownMenuItem>
                              <DropdownMenuItem onClick={() => { setSelectedRule(rule); setIsEditOpen(true); }}>
                                <Edit className="mr-2 h-4 w-4" />
                                Edit
                              </DropdownMenuItem>
                              {rule.status === 'staging' && (
                                <DropdownMenuItem onClick={() => promoteMutation.mutate(rule.id)} disabled={promoteMutation.isPending}>
                                  <Play className="mr-2 h-4 w-4" />
                                  Promote to Active
                                </DropdownMenuItem>
                              )}
                              {rule.status === 'active' && (
                                <DropdownMenuItem onClick={() => demoteMutation.mutate(rule.id)} disabled={demoteMutation.isPending}>
                                  <Pause className="mr-2 h-4 w-4" />
                                  Demote to Staging
                                </DropdownMenuItem>
                              )}
                              <DropdownMenuSeparator />
                              <DropdownMenuItem className="text-destructive" onClick={() => deleteMutation.mutate(rule.id)} disabled={deleteMutation.isPending}>
                                <Trash2 className="mr-2 h-4 w-4" />
                                Delete
                              </DropdownMenuItem>
                            </DropdownMenuContent>
                          </DropdownMenu>
                        </TableCell>
                      </TableRow>
                    ))}
                    {filteredRules?.length === 0 && (
                      <TableRow>
                        <TableCell colSpan={7} className="text-center py-8 text-muted-foreground">No rules found</TableCell>
                      </TableRow>
                    )}
                  </TableBody>
                </Table>
              </div>
              <div className="flex items-center justify-between mt-4">
                <p className="text-sm text-muted-foreground">
                  Showing {(page - 1) * pageSize + 1} to {Math.min(page * pageSize, rulesResponse?.total || 0)} of {rulesResponse?.total || 0} results
                </p>
                <div className="flex gap-2">
                  <Button variant="outline" size="sm" onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}>
                    <ChevronLeft className="h-4 w-4" />
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => setPage(p => p + 1)} disabled={page >= (rulesResponse?.total_pages || 1)}>
                    <ChevronRight className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="builtin" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Built-in Detection Rules ({builtinRules?.length || 0})</CardTitle>
            </CardHeader>
            <CardContent>
              {builtinLoading ? (
                <div className="flex items-center justify-center py-8">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
                </div>
              ) : (
                <div className="table-container">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Rule ID</TableHead>
                        <TableHead>Display Name</TableHead>
                        <TableHead>Type</TableHead>
                        <TableHead>Severity</TableHead>
                        <TableHead>MITRE</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead className="text-right">Actions</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {builtinRules?.map((rule) => (
                        <TableRow key={rule.rule_id}>
                          <TableCell className="font-mono text-sm">{rule.rule_id}</TableCell>
                          <TableCell className="font-medium">{rule.rule_name}</TableCell>
                          <TableCell>{getTypeBadge(rule.category)}</TableCell>
                          <TableCell>{getSeverityBadge(rule.severity)}</TableCell>
                          <TableCell><code className="text-xs text-muted-foreground">{rule.mitre_techniques.join(', ') || '—'}</code></TableCell>
                          <TableCell>{rule.enabled ? <Badge className="badge-success">Enabled</Badge> : <Badge className="badge-offline">Disabled</Badge>}</TableCell>
                          <TableCell className="text-right">
                            <DropdownMenu>
                              <DropdownMenuTrigger asChild>
                                <Button variant="ghost" size="icon" className="h-8 w-8">
                                  <MoreHorizontal className="h-4 w-4" />
                                </Button>
                              </DropdownMenuTrigger>
                              <DropdownMenuContent align="end">
                                <DropdownMenuItem onClick={() => { setSelectedRule(rule); setIsTestOpen(true); }}>
                                  <Eye className="mr-2 h-4 w-4" />
                                  Test Rule
                                </DropdownMenuItem>
                                <DropdownMenuItem onClick={() => { setSelectedRule(rule); setIsEditOpen(true); }}>
                                  <Edit className="mr-2 h-4 w-4" />
                                  Edit
                                </DropdownMenuItem>
                              </DropdownMenuContent>
                            </DropdownMenu>
                          </TableCell>
                        </TableRow>
                      ))}
                      {builtinRules?.length === 0 && (
                        <TableRow>
                          <TableCell colSpan={7} className="text-center py-8 text-muted-foreground">No built-in rules found</TableCell>
                        </TableRow>
                      )}
                    </TableBody>
                  </Table>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}

export default DetectionRulesPage
