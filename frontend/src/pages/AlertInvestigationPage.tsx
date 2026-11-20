"use client"

import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { MoreHorizontal, FileText as FileTextIcon, Cpu, Info, Network, Shield, Flag, FlagOff, Clock, AlertCircle, User, Copy, Plus } from 'lucide-react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@components/ui/card'
import { Button } from '@components/ui/button'
import { Input } from '@components/ui/input'
import { Label } from '@components/ui/label'
import { Badge } from '@components/ui/badge'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@components/ui/tabs'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@components/ui/table'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger, DropdownMenuSeparator } from '@components/ui/dropdown-menu'
import { ScrollArea } from '@components/ui/scroll-area'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@components/ui/tooltip'
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '@components/ui/alert-dialog'
import { Textarea } from '@components/ui/textarea'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@components/ui/select'
import { cn } from '@lib/utils'
import api from '@lib/api'
import { formatDate } from '@lib/utils'
import { toast } from 'sonner'

interface AlertDetail {
  risk_score?: number
  id: string
  agent_id: string
  agent_hostname: string
  rule_id: string
  rule_name: string
  severity: 'critical' | 'high' | 'medium' | 'low' | 'info'
  status: 'new' | 'investigating' | 'true_positive' | 'false_positive' | 'benign' | 'resolved' | 'suppressed'
  mitre_techniques: string[]
  mitre_tactics: string[]
  correlation_key: string
  finding_count: number
  summary: string
  description: string
  evidence_id?: string
  assignee: string | null
  triage_notes: string | null
  triaged_at: string | null
  resolution: string | null
  resolution_notes: string | null
  resolved_at: string | null
  resolved_by: string | null
  created_at: string
  updated_at: string
  evidence: AlertEvidence | null
}

interface AlertEvidence {
  id: string
  alert_id: string
  telemetry_type: 'process' | 'service' | 'startup' | 'eventlog'
  raw_records: any[]
  process_tree: any[]
  network_connections: any[]
  file_hashes: Record<string, string>
  threat_intel: Record<string, any>
  collected_at: string
  size_bytes: number
}

interface AlertDetailResponse {
  alert: AlertDetail
}

interface AlertNote {
  id: string
  note: string
  user_name: string
  created_at: string
}

interface InvestigationReport {
  summary: string
  findings: string[]
  timeline: string[]
  evidence_ids: string[]
  confidence: 'low' | 'medium' | 'high' | string
  recommended_steps: string[]
  limitations: string[]
  provider: string
  model: string
}

interface AIStatus {
  provider: string
  model: string
  available: boolean
  loaded: boolean
  message: string
}

interface AlertHistoryEntry {
  id: string
  alert_id: string
  action: string
  old_status: string | null
  new_status: string
  notes: string | null
  user_id: string
  user_name: string
  created_at: string
}

interface MITRETechnique {
  id: string
  name: string
  description: string
  tactics: string[]
}

function CopyHashButton({ hash }: { hash: string }) {
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => navigator.clipboard.writeText(hash)}>
            <Copy className="h-4 w-4" />
          </Button>
        </TooltipTrigger>
        <TooltipContent>Copied to clipboard</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}

export function AlertInvestigationPage() {
  const { id } = useParams<{ id: string }>()
  const queryClient = useQueryClient()
  const [activeTab, setActiveTab] = useState<string>('overview')
  const [isResolving, setIsResolving] = useState(false)
  const [resolutionData, setResolutionData] = useState({ resolution: '', notes: '' })
  const [isTriageOpen, setIsTriageOpen] = useState(false)
  const [triageData, setTriageData] = useState({ status: '', assignee: '', notes: '' })
  const [newNote, setNewNote] = useState('')
  const [selectedMitre, setSelectedMitre] = useState<{ id: string; name: string; description: string; tactics: string[] } | null>(null)

  const { data: alertDetail, isLoading: alertLoading, error: alertError } = useQuery<AlertDetailResponse>({
    queryKey: ['alert', 'detail', id],
    queryFn: async () => {
      const response = await api.get<AlertDetail>(`/api/v1/alerts/${id}`)
      return { alert: response.data }
    },
    enabled: !!id,
    retry: 1,
  })

  const { data: evidenceData } = useQuery<AlertEvidence>({
    queryKey: ['evidence', id],
    queryFn: async () => {
      const response = await api.get<AlertEvidence>(`/api/v1/alerts/${id}/evidence`)
      return response.data
    },
    enabled: !!id && !!alertDetail?.alert.evidence_id,
    retry: 1,
  })

  const { data: history, isLoading: historyLoading } = useQuery<AlertHistoryEntry[]>({
    queryKey: ['alert', 'history', id],
    queryFn: async () => {
      const response = await api.get<{ history: AlertHistoryEntry[] }>(`/api/v1/alerts/${id}/history`)
      return response.data.history
    },
    enabled: !!id,
    retry: 1,
  })

  const { data: notes } = useQuery<AlertNote[]>({
    queryKey: ['alert', 'notes', id],
    queryFn: async () => (await api.get<{ notes: AlertNote[] }>(`/api/v1/alerts/${id}/notes`)).data.notes,
    enabled: !!id,
  })

  const { data: aiStatus, refetch: refreshAIStatus, isFetching: isRefreshingAIStatus } = useQuery<AIStatus>({
    queryKey: ['ai', 'status'],
    queryFn: async () => (await api.get<AIStatus>('/api/v1/ai/status')).data,
    staleTime: 30_000,
    retry: false,
  })

  const mitreDetails: MITRETechnique[] = []

  const investigationMutation = useMutation({
    mutationFn: async () => (await api.post<InvestigationReport>(`/api/v1/alerts/${id}/investigate`)).data,
    onError: (error: any) => toast.error(error.response?.data?.detail || 'AI investigation failed. Check the local Ollama service.'),
  })

  const triageMutation = useMutation({
    mutationFn: async (data: { status: string; assignee?: string; notes?: string }) => {
      const response = await api.post(`/api/v1/alerts/${id}/triage`, data)
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alert', 'detail', id] })
      queryClient.invalidateQueries({ queryKey: ['alert', 'history', id] })
      queryClient.invalidateQueries({ queryKey: ['alerts'] })
      toast.success('Alert triaged successfully')
      setIsTriageOpen(false)
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to triage alert')
    },
  })

  const resolveMutation = useMutation({
    mutationFn: async (data: { resolution: string; notes?: string }) => {
      const response = await api.post(`/api/v1/alerts/${id}/resolve`, data)
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alert', 'detail', id] })
      queryClient.invalidateQueries({ queryKey: ['alert', 'history', id] })
      queryClient.invalidateQueries({ queryKey: ['alerts'] })
      toast.success('Alert resolved successfully')
      setIsResolving(false)
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to resolve alert')
    },
  })

  const addNoteMutation = useMutation({
    mutationFn: async (note: string) => {
      const response = await api.post(`/api/v1/alerts/${id}/notes`, { note })
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alert', 'history', id] })
      queryClient.invalidateQueries({ queryKey: ['alert', 'notes', id] })
      setNewNote('')
      toast.success('Note added')
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to add note')
    },
  })

  const getSeverityColor = (severity: string) => {
    const colors: Record<string, string> = {
      critical: 'bg-red-500 text-white',
      high: 'bg-orange-500 text-white',
      medium: 'bg-yellow-500 text-white',
      low: 'bg-blue-500 text-white',
      info: 'bg-gray-500 text-white',
    }
    return colors[severity] || 'bg-gray-500 text-white'
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
    return cn('badge', variants[status] || 'badge-info')
  }

  const statusOptions = [
    { value: 'new', label: 'New' },
    { value: 'investigating', label: 'Investigating' },
    { value: 'true_positive', label: 'True Positive' },
    { value: 'false_positive', label: 'False Positive' },
    { value: 'benign', label: 'Benign' },
    { value: 'resolved', label: 'Resolved' },
    { value: 'suppressed', label: 'Suppressed' },
  ]

  const resolutionOptions = [
    { value: 'true_positive', label: 'True Positive' },
    { value: 'false_positive', label: 'False Positive' },
    { value: 'benign', label: 'Benign' },
    { value: 'suppressed', label: 'Suppressed' },
  ]

  if (alertLoading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
      </div>
    )
  }

  if (alertError || !alertDetail) {
    return (
      <div className="flex h-screen items-center justify-center">
        <Card className="w-full max-w-md mx-auto">
          <CardContent className="text-center py-8">
            <AlertCircle className="mx-auto h-12 w-12 text-destructive" />
            <h2 className="mt-4 text-xl font-semibold">Alert Not Found</h2>
            <p className="mt-2 text-muted-foreground">The alert you're looking for doesn't exist or has been removed.</p>
            <Button className="mt-4" onClick={() => window.history.back()}>Go Back</Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  const alert = alertDetail.alert
  const evidence = evidenceData || null
  const mitreTechniques = alert.mitre_techniques || []

  const severityColor = getSeverityColor(alert.severity)
  const statusBadge = getStatusBadge(alert.status)

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6 p-4 bg-card border rounded-lg">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <Badge className={cn('text-sm', severityColor)}>{alert.severity.toUpperCase()}</Badge>
            <Badge className={cn('text-sm', statusBadge)}>{alert.status.replace('_', ' ').toUpperCase()}</Badge>
            {mitreTechniques.length > 0 && (
              <Badge variant="outline" className="text-xs">
                {mitreTechniques[0]}
              </Badge>
            )}
          </div>
          <h1 className="text-2xl font-bold">{alert.summary}</h1>
          <p className="text-muted-foreground text-sm mt-1">{alert.description}</p>
        </div>
        <div className="flex flex-wrap gap-2 ml-auto">
          <Button variant="outline" onClick={() => setIsTriageOpen(true)}>
            <Flag className="mr-2 h-4 w-4" />
            Triage
          </Button>
          <Button variant="outline" onClick={() => setIsResolving(true)}>
            <FlagOff className="mr-2 h-4 w-4" />
            Resolve
          </Button>
          <Button variant="outline" onClick={() => setActiveTab('notes')}>
            <FileTextIcon className="mr-2 h-4 w-4" />
            Add Note
          </Button>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline">
                <MoreHorizontal className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={() => setActiveTab('overview')}>
                <Info className="mr-2 h-4 w-4" /> Overview
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => setActiveTab('evidence')}>
                <Shield className="mr-2 h-4 w-4" /> Evidence
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => setActiveTab('process')}>
                <Cpu className="mr-2 h-4 w-4" /> Process Tree
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => setActiveTab('network')}>
                <Network className="mr-2 h-4 w-4" /> Network
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => setActiveTab('files')}>
                <FileTextIcon className="mr-2 h-4 w-4" /> Files
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => setActiveTab('history')}>
                <Clock className="mr-2 h-4 w-4" /> History
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => setActiveTab('notes')}>
                <FileTextIcon className="mr-2 h-4 w-4" /> Notes
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem className="text-destructive" onClick={() => setIsResolving(true)}>
                <FlagOff className="mr-2 h-4 w-4" /> Resolve
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>

      {/* Tab Navigation */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="mb-4">
        <TabsList className="grid w-full grid-cols-8">
          <TabsTrigger value="overview"><Info className="mr-2 h-4 w-4" /> Overview</TabsTrigger>
          <TabsTrigger value="evidence"><Shield className="mr-2 h-4 w-4" /> Evidence</TabsTrigger>
          <TabsTrigger value="process"><Cpu className="mr-2 h-4 w-4" /> Process Tree</TabsTrigger>
          <TabsTrigger value="network"><Network className="mr-2 h-4 w-4" /> Network</TabsTrigger>
          <TabsTrigger value="files"><FileTextIcon className="mr-2 h-4 w-4" /> Files</TabsTrigger>
          <TabsTrigger value="history"><Clock className="mr-2 h-4 w-4" /> History</TabsTrigger>
          <TabsTrigger value="notes"><FileTextIcon className="mr-2 h-4 w-4" /> Notes</TabsTrigger>
          <TabsTrigger value="ai-investigation"><Shield className="mr-2 h-4 w-4" /> AI Investigation</TabsTrigger>
        </TabsList>

        <TabsContent value="ai-investigation" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>AI Alert Investigation</CardTitle>
              <CardDescription>Correlates this alert with process, service, and Windows event telemetry from the same endpoint around the alert time. Analysis is read-only and uses your configured local Ollama model.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex flex-wrap items-center gap-3 rounded-md border p-3 text-sm">
                <Badge variant={aiStatus?.loaded ? 'default' : 'secondary'}>{aiStatus?.loaded ? 'AI ready' : aiStatus?.available ? 'Model installed' : 'AI unavailable'}</Badge>
                <span>{aiStatus?.message || 'Checking local Ollama…'}</span>
                <span className="text-muted-foreground">{aiStatus?.provider || 'ollama'} / {aiStatus?.model || 'qwen2.5:7b'}</span>
                <Button variant="ghost" size="sm" onClick={() => refreshAIStatus()} disabled={isRefreshingAIStatus}>Check status</Button>
              </div>
              <Button onClick={() => investigationMutation.mutate()} disabled={investigationMutation.isPending}>
                <Shield className="mr-2 h-4 w-4" />
                {investigationMutation.isPending ? 'Investigating…' : 'Investigate alert'}
              </Button>
              {investigationMutation.data && <div className="space-y-4 rounded-lg border p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h3 className="font-semibold">Investigation report</h3>
                  <Badge variant="outline">{investigationMutation.data.confidence} confidence · {investigationMutation.data.model}</Badge>
                </div>
                <p className="text-sm">{investigationMutation.data.summary}</p>
                <div><h4 className="mb-2 text-sm font-semibold">Findings</h4><ul className="list-disc space-y-1 pl-5 text-sm">{investigationMutation.data.findings.map((item, i) => <li key={i}>{item}</li>)}</ul></div>
                <div><h4 className="mb-2 text-sm font-semibold">Timeline</h4><ul className="list-disc space-y-1 pl-5 text-sm">{investigationMutation.data.timeline.map((item, i) => <li key={i}>{item}</li>)}</ul></div>
                <div><h4 className="mb-2 text-sm font-semibold">Recommended next steps</h4><ul className="list-disc space-y-1 pl-5 text-sm">{investigationMutation.data.recommended_steps.map((item, i) => <li key={i}>{item}</li>)}</ul></div>
                {!!investigationMutation.data.limitations.length && <p className="text-xs text-muted-foreground">Limitations: {investigationMutation.data.limitations.join(' ')}</p>}
                <p className="text-xs text-muted-foreground">Evidence records: {investigationMutation.data.evidence_ids.length ? investigationMutation.data.evidence_ids.join(', ') : 'No record IDs cited'}</p>
              </div>}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="overview" className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Alert ID</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold font-mono">{alert.id}</div>
                <p className="text-xs text-muted-foreground">Unique alert identifier</p>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Agent</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{alert.agent_hostname || 'Unknown'}</div>
                <p className="text-xs text-muted-foreground">{alert.agent_id}</p>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Detection Rule</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold font-mono text-sm">{alert.rule_name}</div>
                <p className="text-xs text-muted-foreground">{alert.rule_id}</p>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Risk Score</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{alert.risk_score?.toFixed(1) || '0'}/100</div>
                <p className="text-xs text-muted-foreground">Calculated risk score</p>
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader>
              <CardTitle>MITRE ATT&CK Mapping</CardTitle>
              <CardDescription>Associated techniques and tactics</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {mitreTechniques.map((techniqueId, index) => {
                  const technique = mitreDetails?.find(t => t.id === techniqueId)
                  return (
                    <div key={index} className="flex items-center gap-3 p-3 bg-muted/50 rounded-lg">
                      <Badge variant="outline" className="font-mono text-sm">{techniqueId}</Badge>
                      <div className="flex-1">
                        <p className="font-medium">{technique?.name || 'Unknown Technique'}</p>
                        <p className="text-xs text-muted-foreground">{technique?.description || 'No description available'}</p>
                        <div className="flex gap-1 mt-1">
                          {technique?.tactics?.map((tactic: string) => (
                            <Badge key={tactic} variant="secondary" className="text-xs">{tactic}</Badge>
                          ))}
                        </div>
                      </div>
                    </div>
                  )
                })}
                {mitreTechniques.length === 0 && (
                  <p className="text-muted-foreground text-sm">No MITRE techniques associated</p>
                )}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Alert Details</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <div>
                  <Label className="text-xs font-medium text-muted-foreground">Correlation Key</Label>
                  <p className="font-mono text-sm">{alert.correlation_key || 'N/A'}</p>
                </div>
                <div>
                  <Label className="text-xs font-medium text-muted-foreground">Finding Count</Label>
                  <p className="font-mono text-sm">{alert.finding_count}</p>
                </div>
                <div>
                  <Label className="text-xs font-medium text-muted-foreground">Assignee</Label>
                  <p className="font-mono text-sm">{alert.assignee || 'Unassigned'}</p>
                </div>
                <div>
                  <Label className="text-xs font-medium text-muted-foreground">Created</Label>
                  <p className="font-mono text-sm">{formatDate(alert.created_at)}</p>
                </div>
                <div>
                  <Label className="text-xs font-medium text-muted-foreground">Updated</Label>
                  <p className="font-mono text-sm">{formatDate(alert.updated_at)}</p>
                </div>
                <div>
                  <Label className="text-xs font-medium text-muted-foreground">Triage Time</Label>
                  <p className="font-mono text-sm">{alert.triaged_at ? formatDate(alert.triaged_at) : 'Not triaged'}</p>
                </div>
                <div>
                  <Label className="text-xs font-medium text-muted-foreground">Resolved</Label>
                  <p className="font-mono text-sm">{alert.resolved_at ? formatDate(alert.resolved_at) : 'Not resolved'}</p>
                </div>
                <div>
                  <Label className="text-xs font-medium text-muted-foreground">Resolved By</Label>
                  <p className="font-mono text-sm">{alert.resolved_by || 'N/A'}</p>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="evidence" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Raw Telemetry Records</CardTitle>
              <CardDescription>Raw telemetry records that triggered this alert</CardDescription>
            </CardHeader>
            <CardContent>
              {evidence?.raw_records && evidence.raw_records.length > 0 ? (
                <ScrollArea className="h-[400px]">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Type</TableHead>
                        <TableHead>Key Fields</TableHead>
                        <TableHead>Timestamp</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {evidence.raw_records.map((record: any, index: number) => (
                        <TableRow key={index}>
                          <TableCell className="font-mono text-xs">{record.telemetry_type || 'unknown'}</TableCell>
                          <TableCell className="max-w-md">
                            <pre className="text-xs whitespace-pre-wrap max-h-20 overflow-auto">{JSON.stringify(record, null, 2)}</pre>
                          </TableCell>
                          <TableCell className="font-mono text-xs">{record.collected_at || record.timestamp || 'N/A'}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </ScrollArea>
              ) : (
                <p className="text-muted-foreground text-center py-8">No raw telemetry records available</p>
              )}
            </CardContent>
          </Card>

          {evidence?.process_tree && evidence.process_tree.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Process Tree</CardTitle>
                <CardDescription>Process hierarchy from evidence</CardDescription>
              </CardHeader>
              <CardContent>
                <ScrollArea className="h-[400px]">
                  <pre className="text-xs font-mono whitespace-pre-wrap">{JSON.stringify(evidence.process_tree, null, 2)}</pre>
                </ScrollArea>
              </CardContent>
            </Card>
          )}

          {evidence?.network_connections && evidence.network_connections.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Network Connections</CardTitle>
                <CardDescription>Network connections from evidence</CardDescription>
              </CardHeader>
              <CardContent>
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
                    {evidence.network_connections.map((conn: any, index: number) => (
                      <TableRow key={index}>
                        <TableCell className="font-mono text-xs">{conn.local_address || 'N/A'}</TableCell>
                        <TableCell className="font-mono text-xs">{conn.remote_address || 'N/A'}</TableCell>
                        <TableCell><Badge variant="outline">{conn.status || 'UNKNOWN'}</Badge></TableCell>
                        <TableCell>{conn.protocol || 'N/A'}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          )}

          {evidence?.file_hashes && Object.keys(evidence.file_hashes).length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>File Hashes</CardTitle>
                <CardDescription>File hashes from evidence</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="grid gap-2 md:grid-cols-2">
                  {Object.entries(evidence.file_hashes).map(([algo, hash]) => (
                    <div key={algo} className="flex items-center gap-3 p-3 bg-muted/50 rounded-lg">
                      <Badge variant="outline" className="font-mono text-xs">{algo.toUpperCase()}</Badge>
                      <code className="font-mono text-xs text-muted-foreground flex-1 break-all">{hash}</code>
                      <CopyHashButton hash={hash} />
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {evidence?.threat_intel && Object.keys(evidence.threat_intel).length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Threat Intelligence</CardTitle>
                <CardDescription>Threat intelligence enrichment</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="grid gap-2 md:grid-cols-2">
                  {Object.entries(evidence.threat_intel).map(([key, value]) => (
                    <div key={key} className="flex items-center gap-3 p-3 bg-muted/50 rounded-lg">
                      <Badge variant="outline" className="font-mono text-xs">{key}</Badge>
                      <code className="text-xs text-muted-foreground flex-1 break-all">{String(value)}</code>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        <TabsContent value="process" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Process Tree</CardTitle>
              <CardDescription>Process hierarchy from evidence</CardDescription>
            </CardHeader>
            <CardContent>
              {evidence?.process_tree && evidence.process_tree.length > 0 ? (
                <ScrollArea className="h-[500px]">
                  <pre className="text-xs font-mono whitespace-pre-wrap">{JSON.stringify(evidence.process_tree, null, 2)}</pre>
                </ScrollArea>
              ) : (
                <p className="text-muted-foreground text-center py-8">No process tree data available</p>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="network" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Network Connections</CardTitle>
              <CardDescription>Network connections from evidence and related telemetry</CardDescription>
            </CardHeader>
            <CardContent>
              {evidence?.network_connections && evidence.network_connections.length > 0 ? (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Local Address</TableHead>
                      <TableHead>Remote Address</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Protocol</TableHead>
                      <TableHead>PID</TableHead>
                      <TableHead>Process</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {evidence.network_connections.map((conn: any, index: number) => (
                      <TableRow key={index}>
                        <TableCell className="font-mono text-xs">{conn.local_address || 'N/A'}</TableCell>
                        <TableCell className="font-mono text-xs">{conn.remote_address || 'N/A'}</TableCell>
                        <TableCell><Badge variant="outline">{conn.status || 'UNKNOWN'}</Badge></TableCell>
                        <TableCell>{conn.protocol || 'N/A'}</TableCell>
                        <TableCell className="font-mono text-xs">{conn.pid || 'N/A'}</TableCell>
                        <TableCell>{conn.process_name || 'N/A'}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              ) : (
                <p className="text-muted-foreground text-center py-8">No network connection data available</p>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="files" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>File Artifacts</CardTitle>
              <CardDescription>File hashes and artifacts from evidence</CardDescription>
            </CardHeader>
            <CardContent>
              {evidence?.file_hashes && Object.keys(evidence.file_hashes).length > 0 ? (
                <div className="grid gap-2 md:grid-cols-2">
                  {Object.entries(evidence.file_hashes).map(([algo, hash]) => (
                    <div key={algo} className="flex items-center gap-3 p-3 bg-muted/50 rounded-lg">
                      <Badge variant="outline" className="font-mono text-xs">{algo.toUpperCase()}</Badge>
                      <code className="font-mono text-xs text-muted-foreground flex-1 break-all">{hash}</code>
                      <CopyHashButton hash={hash} />
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-muted-foreground text-center py-8">No file hashes available</p>
              )}
            </CardContent>
          </Card>

          {evidence?.threat_intel && Object.keys(evidence.threat_intel).length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Threat Intelligence</CardTitle>
                <CardDescription>Threat intelligence enrichment</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="grid gap-2 md:grid-cols-2">
                  {Object.entries(evidence.threat_intel).map(([key, value]) => (
                    <div key={key} className="flex items-center gap-3 p-3 bg-muted/50 rounded-lg">
                      <Badge variant="outline" className="font-mono text-xs">{key}</Badge>
                      <code className="text-xs text-muted-foreground flex-1 break-all">{String(value)}</code>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        <TabsContent value="network" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Network Analysis</CardTitle>
              <CardDescription>Network connections and related telemetry</CardDescription>
            </CardHeader>
            <CardContent>
              <p className="text-muted-foreground text-center py-8">Network analysis features coming soon</p>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="files" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>File Analysis</CardTitle>
              <CardDescription>File artifacts and metadata</CardDescription>
            </CardHeader>
            <CardContent>
              <p className="text-muted-foreground text-center py-8">File analysis features coming soon</p>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="history" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Alert History</CardTitle>
              <CardDescription>Timeline of alert status changes and analyst actions</CardDescription>
            </CardHeader>
            <CardContent>
              {historyLoading ? (
                <div className="flex items-center justify-center py-8">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
                </div>
              ) : history && history.length > 0 ? (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Timestamp</TableHead>
                      <TableHead>Action</TableHead>
                      <TableHead>Previous Status</TableHead>
                      <TableHead>New Status</TableHead>
                      <TableHead>Analyst</TableHead>
                      <TableHead>Notes</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {history.map((entry: AlertHistoryEntry, index: number) => (
                      <TableRow key={index}>
                        <TableCell className="font-mono text-sm">{formatDate(entry.created_at)}</TableCell>
                        <TableCell>
                          <Badge variant="outline" className="text-xs">{entry.action.replace('_', ' ').toUpperCase()}</Badge>
                        </TableCell>
                        <TableCell className="font-mono text-xs">{entry.old_status || 'N/A'}</TableCell>
                        <TableCell className="font-mono text-xs">{entry.new_status}</TableCell>
                        <TableCell>{entry.user_name || entry.user_id}</TableCell>
                        <TableCell className="text-muted-foreground text-sm max-w-xs truncate">{entry.notes || '—'}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              ) : (
                <p className="text-muted-foreground text-center py-8">No history available</p>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="notes" className="space-y-4">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle>Investigation Notes</CardTitle>
              <CardDescription>Analyst notes and observations</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex gap-2">
                <Textarea
                  placeholder="Add investigation note..."
                  value={newNote}
                  onChange={(e) => setNewNote(e.target.value)}
                  className="flex-1 min-h-[80px]"
                  rows={3}
                />
                <Button onClick={() => addNoteMutation.mutate(newNote)} disabled={!newNote.trim() || addNoteMutation.isPending}>
                  <Plus className="mr-2 h-4 w-4" />
                  {addNoteMutation.isPending ? 'Adding...' : 'Add Note'}
                </Button>
              </div>

              <div className="space-y-3">
                {(notes || []).map((note) => (
                  <div key={note.id} className="p-4 bg-muted/50 rounded-lg border">
                    <div className="flex items-start justify-between gap-2 mb-2">
                      <div className="flex items-center gap-2">
                        <User className="h-4 w-4 text-muted-foreground" />
                        <span className="text-sm font-medium text-muted-foreground">Analyst</span>
                        <span className="text-xs text-muted-foreground">{formatDate(note.created_at)}</span>
                      </div>
                    </div>
                    <p className="text-sm whitespace-pre-wrap">{note.note}</p>
                  </div>
                ))}
                {(notes || []).length === 0 && (
                  <p className="text-muted-foreground text-center py-8">No investigation notes yet</p>
                )}
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Triage Dialog */}
      <AlertDialog open={isTriageOpen} onOpenChange={setIsTriageOpen}>
        <AlertDialogContent className="max-w-md">
          <AlertDialogHeader>
            <AlertDialogTitle>Triage Alert</AlertDialogTitle>
            <AlertDialogDescription>Update the alert status and assign to an analyst</AlertDialogDescription>
          </AlertDialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="triage-status">Status</Label>
              <Select value={triageData.status} onValueChange={(value) => setTriageData({ ...triageData, status: value })}>
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="Select status" />
                </SelectTrigger>
                <SelectContent>
                  {statusOptions.map((option) => (
                    <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="triage-assignee">Assignee</Label>
              <Input
                id="triage-assignee"
                placeholder="Analyst username"
                value={triageData.assignee}
                onChange={(e) => setTriageData({ ...triageData, assignee: e.target.value })}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="triage-notes">Notes</Label>
              <Textarea
                id="triage-notes"
                placeholder="Triage notes..."
                value={triageData.notes}
                onChange={(e) => setTriageData({ ...triageData, notes: e.target.value })}
                rows={3}
              />
            </div>
          </div>
          <AlertDialogFooter>
            <AlertDialogCancel onClick={() => setIsTriageOpen(false)}>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={() => triageMutation.mutate(triageData)} disabled={triageMutation.isPending}>
              {triageMutation.isPending ? 'Triaging...' : 'Triage Alert'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Resolve Dialog */}
      <AlertDialog open={isResolving} onOpenChange={setIsResolving}>
        <AlertDialogContent className="max-w-md">
          <AlertDialogHeader>
            <AlertDialogTitle>Resolve Alert</AlertDialogTitle>
            <AlertDialogDescription>Resolve this alert with a disposition</AlertDialogDescription>
          </AlertDialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="resolution">Resolution</Label>
              <Select value={resolutionData.resolution} onValueChange={(v) => setResolutionData({ ...resolutionData, resolution: v })}>
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="Select resolution" />
                </SelectTrigger>
                <SelectContent>
                  {resolutionOptions.map((option) => (
                    <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="resolution-notes">Notes</Label>
              <Textarea
                id="resolution-notes"
                placeholder="Resolution notes..."
                value={resolutionData.notes}
                onChange={(e) => setResolutionData({ ...resolutionData, notes: e.target.value })}
                rows={3}
              />
            </div>
          </div>
          <AlertDialogFooter>
            <AlertDialogCancel onClick={() => setIsResolving(false)}>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={() => resolveMutation.mutate(resolutionData)} disabled={resolveMutation.isPending || !resolutionData.resolution}>
              {resolveMutation.isPending ? 'Resolving...' : 'Resolve Alert'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* MITRE Technique Dialog */}
      {selectedMitre && (
        <AlertDialog open={!!selectedMitre} onOpenChange={() => setSelectedMitre(null)}>
          <AlertDialogContent className="max-w-2xl">
            <AlertDialogHeader>
              <AlertDialogTitle>{selectedMitre.name} ({selectedMitre.id})</AlertDialogTitle>
              <AlertDialogDescription>{selectedMitre.description}</AlertDialogDescription>
            </AlertDialogHeader>
            <div className="space-y-4 py-4">
              <div>
                <Label className="font-medium mb-2 block">Tactics</Label>
                <div className="flex flex-wrap gap-2">
                  {selectedMitre.tactics.map((tactic: string) => (
                    <Badge key={tactic} variant="secondary">{tactic}</Badge>
                  ))}
                </div>
              </div>
              <div>
                <Label className="font-medium mb-2 block">Description</Label>
                <p className="text-sm text-muted-foreground">{selectedMitre.description}</p>
              </div>
            </div>
            <AlertDialogFooter>
              <AlertDialogAction onClick={() => setSelectedMitre(null)}>Close</AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      )}
    </div>
  )
}

export default AlertInvestigationPage
