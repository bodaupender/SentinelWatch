"use client"

import { useState } from 'react'
import { Search, Plus, MoreHorizontal, Play, Pause, ChevronLeft, ChevronRight } from 'lucide-react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@components/ui/table'
import { Input } from '@components/ui/input'
import { Badge } from '@components/ui/badge'
import { Button } from '@components/ui/button'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@components/ui/dropdown-menu'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@components/ui/tabs'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@components/ui/select'
import api from '@lib/api'
import { toast } from 'sonner'

interface DetectionRule {
  id: string
  rule_name: string
  display_name: string
  description: string
  rule_type: 'process' | 'service' | 'startup' | 'eventlog' | 'correlation'
  severity: 'critical' | 'high' | 'medium' | 'low' | 'info'
  status: 'active' | 'staging' | 'disabled' | 'draft' | 'deprecated'
  mitre_techniques: string[]
  mitre_tactics: string[]
  condition: string
  confidence: number
  false_positive_rate: number
  created_at: string
  updated_at: string
  version: number
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
  category: string
  severity: string
  mitre_techniques: string[]
  enabled: boolean
}

export function DetectionRulesPage() {
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [pageSize] = useState(50)
  const [typeFilter, setTypeFilter] = useState('all')
  const [statusFilter, setStatusFilter] = useState('all')
  const [selectedRule, setSelectedRule] = useState<any>(null)
  const [isTestOpen, setIsTestOpen] = useState(false)
  const [isEditOpen, setIsEditOpen] = useState(false)
  const [isCreateOpen, setIsCreateOpen] = useState(false)
  const [activeTab, setActiveTab] = useState<string>('custom')

  const queryClient = useQueryClient()

  const { data: rulesResponse } = useQuery({
    queryKey: ['rules', page, pageSize, typeFilter, statusFilter, search],
    queryFn: async () => {
      const params = new URLSearchParams({
        page: page.toString(),
        limit: pageSize.toString(),
        ...(typeFilter !== 'all' && { rule_type: typeFilter }),
        ...(statusFilter !== 'all' && { status: statusFilter }),
        ...(search && { search }),
      })
      const response = await api.get<{ data: any[]; total: number; page: number; page_size: number; total_pages: number }>(`/api/v1/rules?${params.toString()}`)
      return response.data
    },
    placeholderData: { data: [], total: 0, page: 1, page_size: 50, total_pages: 1 },
  })

  const { data: builtinRules } = useQuery({
    queryKey: ['builtin-rules'],
    queryFn: async () => {
      const response = await api.get('/api/v1/rules/builtin')
      return response.data
    },
  })

  const filteredRules = rulesResponse?.data?.filter((rule) => {
    const matchesSearch = rule.display_name.toLowerCase().includes(search.toLowerCase()) ||
      rule.rule_name.toLowerCase().includes(search.toLowerCase())
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
    const colors: Record<string, string> = {
      process: 'bg-blue-100 text-blue-800',
      service: 'bg-green-100 text-green-800',
      startup: 'bg-purple-100 text-purple-800',
      eventlog: 'bg-orange-100 text-orange-800',
      correlation: 'bg-red-100 text-red-800',
    }
    return <Badge className={colors[type] || 'badge-info'}>{type}</Badge>
  }

  const getSeverityBadge = (severity: string) => {
    const colors: Record<string, string> = {
      critical: 'badge-critical',
      high: 'badge-high',
      medium: 'badge-medium',
      low: 'badge-low',
      info: 'badge-info',
    }
    return <Badge className={colors[severity] || 'badge-info'}>{severity}</Badge>
  }

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
                        <TableCell className="font-mono text-sm">{rule.rule_name}</TableCell>
                        <TableCell className="font-medium">{rule.display_name}</TableCell>
                        <TableCell>{getTypeBadge(rule.rule_type)}</TableCell>
                        <TableCell>{getSeverityBadge(rule.severity)}</TableCell>
                        <TableCell><code className="text-xs text-muted-foreground">{rule.mitre_techniques.join(', ') || '—'}</code></TableCell>
                        <TableCell>{getStatusBadge(rule.status)}</TableCell>
                        <TableCell className="text-right">
                          <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                              <Button variant="ghost" size="icon" className="h-8 w-8">
                                <MoreHorizontal className="h-4 w-4" />
                              </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end">
                              <DropdownMenuItem onClick={() => { setSelectedRule(rule); setIsTestOpen(true); }}>Test Rule</DropdownMenuItem>
                              <DropdownMenuItem onClick={() => { setSelectedRule(rule); setIsEditOpen(true); }}>Edit</DropdownMenuItem>
                              {rule.status === 'staging' && <DropdownMenuItem onClick={() => promoteMutation.mutate(rule.id)}>Promote to Active</DropdownMenuItem>}
                              {rule.status === 'active' && <DropdownMenuItem onClick={() => demoteMutation.mutate(rule.id)}>Demote to Staging</DropdownMenuItem>}
                              <DropdownMenuItem className="text-destructive" onClick={() => deleteMutation.mutate(rule.id)}>Delete</DropdownMenuItem>
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
                    {builtinRules?.map((rule: BuiltinRule) => (
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
                              <DropdownMenuItem onClick={() => { setSelectedRule(rule); setIsTestOpen(true); }}>Test Rule</DropdownMenuItem>
                              <DropdownMenuItem onClick={() => { setSelectedRule(rule); setIsEditOpen(true); }}>Edit</DropdownMenuItem>
                            </DropdownMenuContent>
                          </DropdownMenu>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}

export default DetectionRulesPage
