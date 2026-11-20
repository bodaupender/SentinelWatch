import { useState } from 'react'
import { Plus, Trash2, Clock, Shield, AlertCircle, Copy, Check, X, Loader2, Search, MoreHorizontal, ChevronLeft, ChevronRight } from 'lucide-react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@components/ui/table'
import { Input } from '@components/ui/input'
import { Badge } from '@components/ui/badge'
import { Button } from '@components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@components/ui/dialog'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@components/ui/dropdown-menu'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@components/ui/select'
import { Label } from '@components/ui/label'
import { Textarea } from '@components/ui/textarea'
import { cn } from '@lib/utils'
import api from '@lib/api'

interface EnrollmentToken {
  id: string
  name: string
  description: string | null
  token_prefix: string
  status: 'active' | 'used' | 'expired' | 'revoked'
  expires_at: string | null
  used_count: number
  max_uses: number
  used_at: string | null
  used_by_agent_id: string | null
  revoked_at: string | null
  revoked_by: string | null
  revoked_reason: string | null
  created_by: string | null
  created_at: string
  updated_at: string
}

interface EnrollmentTokenListResponse {
  data: EnrollmentToken[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

interface EnrollmentTokenCreateRequest {
  name: string
  description?: string
  expires_in_days?: number
  max_uses: number
}

interface EnrollmentTokenCreateResponse {
  id: string
  token: string
  token_prefix: string
  message: string
}

export function EnrollmentTokensPage() {
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [statusFilter, setStatusFilter] = useState('all')
  const [createDialogOpen, setCreateDialogOpen] = useState(false)
  const [revokeDialogOpen, setRevokeDialogOpen] = useState(false)
  const [selectedToken, setSelectedToken] = useState<EnrollmentToken | null>(null)
  const [newTokenData, setNewTokenData] = useState({
    name: '',
    description: '',
    expires_in_days: 30,
    max_uses: 1,
  })
  const [revokeReason, setRevokeReason] = useState('')
  const [showNewToken, setShowNewToken] = useState<{ token: string; prefix: string } | null>(null)

  const { data: tokensResponse, isLoading, error, refetch } = useQuery<{
    data: EnrollmentToken[]
    total: number
    page: number
    page_size: number
    total_pages: number
  }>({
    queryKey: ['enrollmentTokens', page, pageSize, statusFilter, search],
    queryFn: async () => {
      const params = new URLSearchParams({
        page: page.toString(),
        limit: pageSize.toString(),
        ...(statusFilter !== 'all' && { status: statusFilter }),
        ...(search && { search }),
      })
      const response = await api.get(`/api/v1/enrollment-tokens?${params.toString()}`)
      return response.data
    },
  })

  const createMutation = useMutation({
    mutationFn: async (data: EnrollmentTokenCreateRequest) => {
      const response = await api.post<{ id: string; token: string; token_prefix: string }>('/api/v1/enrollment-tokens', data)
      return response.data
    },
    onSuccess: (data) => {
      refetch()
      setShowNewToken({ token: data.token, prefix: data.token_prefix })
      setCreateDialogOpen(false)
      setNewTokenData({ name: '', description: '', expires_in_days: 30, max_uses: 1 })
    },
    onError: (error: any) => {
      alert(`Failed to create token: ${error.response?.data?.detail || error.message}`)
    },
  })

  const revokeMutation = useMutation({
    mutationFn: async ({ id, reason }: { id: string; reason: string }) => {
      await api.post(`/api/v1/enrollment-tokens/${id}/revoke`, { reason })
    },
    onSuccess: () => {
      refetch()
      setRevokeDialogOpen(false)
      setSelectedToken(null)
      setRevokeReason('')
    },
    onError: (error: any) => {
      alert(`Failed to revoke token: ${error.response?.data?.detail || error.message}`)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/api/v1/enrollment-tokens/${id}`)
    },
    onSuccess: () => {
      refetch()
    },
    onError: (error: any) => {
      alert(`Failed to delete token: ${error.response?.data?.detail || error.message}`)
    },
  })

  const handleCreate = (e: React.FormEvent) => {
    e.preventDefault()
    createMutation.mutate(newTokenData)
  }

  const handleRevoke = (e: React.FormEvent) => {
    e.preventDefault()
    if (selectedToken) {
      revokeMutation.mutate({ id: selectedToken.id, reason: revokeReason })
    }
  }

  const handleDelete = (id: string) => {
    if (confirm('Are you sure you want to delete this token? This action cannot be undone.')) {
      deleteMutation.mutate(id)
    }
  }

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text)
    alert('Token copied to clipboard!')
  }

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'active':
        return <Badge className="badge-active bg-green-100 text-green-800"><Shield className="mr-1 h-3 w-3" /> Active</Badge>
      case 'used':
        return <Badge className="badge-used bg-blue-100 text-blue-800"><Check className="mr-1 h-3 w-3" /> Used</Badge>
      case 'expired':
        return <Badge className="badge-expired bg-gray-100 text-gray-800"><Clock className="mr-1 h-3 w-3" /> Expired</Badge>
      case 'revoked':
        return <Badge className="badge-revoked bg-red-100 text-red-800"><X className="mr-1 h-3 w-3" /> Revoked</Badge>
      default:
        return <Badge>{status}</Badge>
    }
  }

  const filteredTokens = tokensResponse?.data || []

  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <Loader2 className="animate-spin h-8 w-8 text-primary" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Enrollment Tokens</h1>
          <p className="text-muted-foreground">Manage enrollment tokens for agent registration</p>
        </div>
        <Button onClick={() => setCreateDialogOpen(true)}>
          <Plus className="mr-2 h-4 w-4" />
          Create Token
        </Button>
      </div>

      {showNewToken && (
        <Card className="border-green-500 bg-green-50">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-green-800">New Token Created</CardTitle>
            <Button variant="ghost" size="icon" onClick={() => setShowNewToken(null)}>
              <X className="h-4 w-4" />
            </Button>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="rounded-md border border-green-200 bg-green-50 p-4">
              <p className="text-sm font-medium text-green-800">Store this token securely - it will not be shown again!</p>
              <div className="flex gap-2 mt-2">
                <Input
                  readOnly
                  value={showNewToken.token}
                  className="flex-1 font-mono text-sm"
                />
                <Button variant="outline" size="sm" onClick={() => copyToClipboard(showNewToken.token)}>
                  <Copy className="mr-2 h-4 w-4" />
                  Copy
                </Button>
              </div>
            </div>
            <p className="text-sm text-muted-foreground">
              Prefix: <code className="font-mono">{showNewToken.prefix}</code>
            </p>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            <CardTitle>Enrollment Tokens ({tokensResponse?.data?.length || 0})</CardTitle>
            <div className="flex items-center gap-2">
              <div className="relative w-64">
                <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  placeholder="Search tokens..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  className="pl-10"
                />
              </div>
              <Select value={statusFilter} onValueChange={setStatusFilter}>
                <SelectTrigger className="w-40">
                  <SelectValue placeholder="All Status" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Status</SelectItem>
                  <SelectItem value="active">Active</SelectItem>
                  <SelectItem value="used">Used</SelectItem>
                  <SelectItem value="expired">Expired</SelectItem>
                  <SelectItem value="revoked">Revoked</SelectItem>
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
                  <TableHead>Prefix</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Uses</TableHead>
                  <TableHead>Expires</TableHead>
                  <TableHead>Created</TableHead>
                  <TableHead>Created By</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredTokens.map((token) => (
                  <TableRow key={token.id}>
                    <TableCell className="font-medium">{token.name}</TableCell>
                    <TableCell><code className="font-mono text-sm">{token.token_prefix}</code></TableCell>
                    <TableCell>{getStatusBadge(token.status)}</TableCell>
                    <TableCell>{token.used_count} / {token.max_uses}</TableCell>
                    <TableCell>
                      {token.expires_at ? formatDateLocal(token.expires_at) : 'Never'}
                    </TableCell>
                    <TableCell>{formatDateLocal(token.created_at)}</TableCell>
                    <TableCell>{token.created_by || '—'}</TableCell>
                    <TableCell className="text-right">
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon" className="h-8 w-8">
                            <MoreHorizontal className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem onClick={() => setShowNewToken({ token: '', prefix: token.token_prefix })}>
                            <Copy className="mr-2 h-4 w-4" /> Copy Prefix
                          </DropdownMenuItem>
                          <DropdownMenuItem onClick={() => { setSelectedToken(token); setRevokeDialogOpen(true); }}>
                            <Shield className="mr-2 h-4 w-4" /> Revoke
                          </DropdownMenuItem>
                          <DropdownMenuItem className="text-destructive" onClick={() => deleteMutation.mutate(token.id)}>
                            <Trash2 className="mr-2 h-4 w-4" /> Delete
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
              Showing {(page - 1) * pageSize + 1} to {Math.min(page * pageSize, (tokensResponse?.total || 0))} of {tokensResponse?.total || 0} results
            </p>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}>
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <Button variant="outline" size="sm" onClick={() => setPage(p => p + 1)} disabled={page >= (tokensResponse?.total_pages || 1)}>
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Create Token Dialog */}
      <Dialog open={createDialogOpen} onOpenChange={setCreateDialogOpen}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Create Enrollment Token</DialogTitle>
            <DialogDescription>
              Generate a new token for agent enrollment. The full token will only be shown once.
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={handleCreate}>
            <div className="space-y-4 py-4">
              <div className="grid gap-4">
                <div className="space-y-2">
                  <Label htmlFor="name">Name *</Label>
                  <Input
                    id="name"
                    value={newTokenData.name}
                    onChange={(e) => setNewTokenData({ ...newTokenData, name: e.target.value })}
                    placeholder="e.g., Windows Workstations Q1 2026"
                    required
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="description">Description</Label>
                  <Textarea
                    id="description"
                    value={newTokenData.description}
                    onChange={(e) => setNewTokenData({ ...newTokenData, description: e.target.value })}
                    placeholder="Optional description"
                    rows={3}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="expires_in_days">Expires in (days)</Label>
                  <Input
                    id="expires_in_days"
                    type="number"
                    min="1"
                    max="365"
                    value={newTokenData.expires_in_days}
                    onChange={(e) => setNewTokenData({ ...newTokenData, expires_in_days: parseInt(e.target.value) || 30 })}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="max_uses">Max Uses</Label>
                  <Input
                    id="max_uses"
                    type="number"
                    min="1"
                    max="1000"
                    value={newTokenData.max_uses}
                    onChange={(e) => setNewTokenData({ ...newTokenData, max_uses: parseInt(e.target.value) || 1 })}
                  />
                </div>
              </div>
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setCreateDialogOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={createMutation.isPending}>
                {createMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Create
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Revoke Token Dialog */}
      <Dialog open={revokeDialogOpen} onOpenChange={setRevokeDialogOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Revoke Enrollment Token</DialogTitle>
            <DialogDescription>
              This will permanently revoke the token. It can no longer be used for agent enrollment.
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={handleRevoke}>
            <div className="space-y-4 py-4">
              <p className="text-sm text-muted-foreground">
                Revoking token: <code className="font-mono">{selectedToken?.token_prefix}</code> ({selectedToken?.name})
              </p>
              <div className="space-y-2">
                <Label htmlFor="revoke_reason">Reason *</Label>
                <Textarea
                  id="revoke_reason"
                  value={revokeReason}
                  onChange={(e) => setRevokeReason(e.target.value)}
                  placeholder="Reason for revocation"
                  rows={3}
                  required
                />
              </div>
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setRevokeDialogOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" variant="destructive" disabled={revokeMutation.isPending}>
                {revokeMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Revoke
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  )
}

function getStatusBadge(status: string) {
  switch (status) {
    case 'active':
      return <Badge className="bg-green-100 text-green-800"><Shield className="mr-1 h-3 w-3" /> Active</Badge>
    case 'used':
      return <Badge className="bg-blue-100 text-blue-800"><Check className="mr-1 h-3 w-3" /> Used</Badge>
    case 'expired':
      return <Badge className="bg-gray-100 text-gray-800"><Clock className="mr-1 h-3 w-3" /> Expired</Badge>
    case 'revoked':
      return <Badge className="bg-red-100 text-red-800"><X className="mr-1 h-3 w-3" /> Revoked</Badge>
    default:
      return <Badge>{status}</Badge>
  }
}

function formatDateLocal(dateString: string) {
  const date = new Date(dateString)
  return date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

export default EnrollmentTokensPage
