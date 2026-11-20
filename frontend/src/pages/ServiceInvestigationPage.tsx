import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { ServerCog, Shield, Clock, Info, Server, ServerOff, Pause } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@components/ui/table'
import { Badge } from '@components/ui/badge'
import { Button } from '@components/ui/button'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@components/ui/dropdown-menu'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@components/ui/tabs'
import api from '@lib/api'

interface ServiceDetail {
  id: string
  agent_id: string
  agent_hostname: string
  name: string
  display_name: string
  status: 'RUNNING' | 'STOPPED' | 'PAUSED' | 'START_PENDING' | 'STOP_PENDING' | 'CONTINUE_PENDING' | 'PAUSE_PENDING'
  start_type: 'AUTO' | 'MANUAL' | 'DISABLED' | 'DELAYED_AUTO'
  binary_path: string
  service_type: string
  dependencies: string[]
  account: string
  exe_sha256: string
  signature_info: {
    is_signed: boolean
    signer_name: string
    issuer_name: string
    timestamp: string
    is_trusted: boolean
  }
  config_audit: {
    is_path_quoted: boolean
    has_spaces_in_path: boolean
    is_unquoted_with_spaces: boolean
    path_exists: boolean
    binary_writable_by_user: boolean
    directory_writable_by_user: boolean
    binary_owner: string
    directory_owner: string
    is_in_writable_location: boolean
    has_suspicious_name: boolean
    has_suspicious_binary_name: boolean
  }
  created_at: string
  updated_at: string
}

export function ServiceInvestigationPage() {
  const { id } = useParams<{ id: string }>()
  const [activeTab, setActiveTab] = useState<string>('overview')

  const { data: service, isLoading } = useQuery<ServiceDetail>({
    queryKey: ['service', 'detail', id],
    queryFn: async () => {
      const response = await api.get(`/api/v1/services/${id}`)
      return response.data
    },
    enabled: !!id,
  })

  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
      </div>
    )
  }

  if (!service) {
    return (
      <div className="flex h-screen items-center justify-center">
        <Card className="w-full max-w-md mx-auto">
          <CardContent className="text-center py-8">
            <ServerCog className="mx-auto h-12 w-12 text-destructive" />
            <h2 className="mt-4 text-xl font-semibold">Service Not Found</h2>
            <p className="mt-2 text-muted-foreground">The service you're looking for doesn't exist or has been removed.</p>
            <Button className="mt-4" onClick={() => window.history.back()}>Go Back</Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  const serviceData = service

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Service Investigation</h1>
          <p className="text-muted-foreground">Investigate service details and configuration</p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="outline" className="text-sm">
            <ServerCog className="mr-2 h-4 w-4" />
            {serviceData.display_name || serviceData.name}
          </Badge>
        </div>
      </div>

      <Tabs value={activeTab} onValueChange={(value: string) => setActiveTab(value as 'overview' | 'config' | 'security' | 'history')} className="mb-4">
        <TabsList className="grid w-full grid-cols-4">
          <TabsTrigger value="overview"><Info className="mr-2 h-4 w-4" /> Overview</TabsTrigger>
          <TabsTrigger value="config"><ServerCog className="mr-2 h-4 w-4" /> Configuration</TabsTrigger>
          <TabsTrigger value="security"><Shield className="mr-2 h-4 w-4" /> Security</TabsTrigger>
          <TabsTrigger value="history"><Clock className="mr-2 h-4 w-4" /> History</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="space-y-6">
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Service Name</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{service.name}</div>
                <p className="text-xs text-muted-foreground">{service.display_name}</p>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Status</CardTitle>
              </CardHeader>
              <CardContent>
                {getStatusBadge(service.status)}
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Start Type</CardTitle>
              </CardHeader>
              <CardContent>
                {getStartTypeBadge(service.start_type)}
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Account</CardTitle>
              </CardHeader>
              <CardContent>
                <span className="text-sm font-mono">{service.account}</span>
              </CardContent>
            </Card>
          </div>

          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            <Card>
              <CardHeader>
                <CardTitle>Binary Path</CardTitle>
              </CardHeader>
              <CardContent>
                <code className="text-xs text-muted-foreground break-all">{service.binary_path}</code>
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Service Type</CardTitle>
              </CardHeader>
              <CardContent>
                <Badge variant="outline">{service.service_type}</Badge>
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Dependencies</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex flex-wrap gap-1">
                  {service.dependencies.map((dep, i) => (
                    <Badge key={i} variant="outline" className="text-xs">{dep}</Badge>
                  ))}
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>SHA256</CardTitle>
              </CardHeader>
              <CardContent>
                <code className="font-mono text-xs">{service.exe_sha256 || 'N/A'}</code>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="config" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Service Configuration</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid gap-4 md:grid-cols-2">
                <div>
                  <div className="text-sm font-medium text-muted-foreground">Binary Path</div>
                  <div className="font-mono text-sm break-all">{service.binary_path}</div>
                </div>
                <div>
                  <div className="text-sm font-medium text-muted-foreground">Service Type</div>
                  <div>{service.service_type}</div>
                </div>
                <div>
                  <div className="text-sm font-medium text-muted-foreground">Start Type</div>
                  <div>{getStartTypeBadge(service.start_type)}</div>
                </div>
                <div>
                  <div className="text-sm font-medium text-muted-foreground">Account</div>
                  <div>{service.account}</div>
                </div>
                <div>
                  <div className="text-sm font-medium text-muted-foreground">Dependencies</div>
                  <div>
                    <div className="flex flex-wrap gap-1">
                      {service.dependencies.map((dep, i) => (
                        <Badge key={i} variant="outline" className="text-xs">{dep}</Badge>
                      ))}
                    </div>
                  </div>
                </div>
                <div>
                  <div className="text-sm font-medium text-muted-foreground">SHA256</div>
                  <div className="font-mono text-xs">{service.exe_sha256 || 'N/A'}</div>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="security" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Security Audit</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <div className="text-sm font-medium">Path Quoted</div>
                  <div>{service.config_audit.is_path_quoted ? (
                    <Badge className="badge-success">Yes</Badge>
                  ) : (
                    <Badge className="badge-destructive">No</Badge>
                  )}</div>
                </div>
                <div className="space-y-2">
                  <div className="text-sm font-medium text-muted-foreground">Has Spaces in Path</div>
                  <div>{service.config_audit.has_spaces_in_path ? (
                    <Badge className="badge-destructive">Yes</Badge>
                  ) : (
                    <Badge className="badge-success">No</Badge>
                  )}</div>
                </div>
                <div className="space-y-2">
                  <div className="text-sm font-medium text-muted-foreground">Unquoted with Spaces</div>
                  <div>{service.config_audit.is_unquoted_with_spaces ? (
                    <Badge className="badge-destructive">Yes - Risk</Badge>
                  ) : (
                    <Badge className="badge-success">No</Badge>
                  )}</div>
                </div>
                <div className="space-y-2">
                  <div className="text-sm font-medium text-muted-foreground">Path Exists</div>
                  <div>{service.config_audit.path_exists ? (
                    <Badge className="badge-success">Yes</Badge>
                  ) : (
                    <Badge className="badge-destructive">No - Missing</Badge>
                  )}</div>
                </div>
                <div className="space-y-2">
                  <div className="text-sm font-medium text-muted-foreground">Binary Writable by User</div>
                  <div>{service.config_audit.binary_writable_by_user ? (
                    <Badge className="badge-destructive">Yes - Risk</Badge>
                  ) : (
                    <Badge className="badge-success">No</Badge>
                  )}</div>
                </div>
                <div className="space-y-2">
                  <div className="text-sm font-medium text-muted-foreground">Directory Writable by User</div>
                  <div>{service.config_audit.directory_writable_by_user ? (
                    <Badge className="badge-destructive">Yes - Risk</Badge>
                  ) : (
                    <Badge className="badge-success">No</Badge>
                  )}</div>
                </div>
                <div className="space-y-2">
                  <div className="text-sm font-medium text-muted-foreground">Binary Owner</div>
                  <div className="font-mono text-sm">{service.config_audit.binary_owner}</div>
                </div>
                <div className="space-y-2">
                  <div className="text-sm font-medium text-muted-foreground">Directory Owner</div>
                  <div className="font-mono text-sm">{service.config_audit.directory_owner}</div>
                </div>
                <div className="space-y-2">
                  <div className="text-sm font-medium text-muted-foreground">Suspicious Name</div>
                  <div>{service.config_audit.has_suspicious_name ? (
                    <Badge className="badge-destructive">Yes - Risk</Badge>
                  ) : (
                    <Badge className="badge-success">No</Badge>
                  )}</div>
                </div>
                <div className="space-y-2">
                  <div className="text-sm font-medium text-muted-foreground">Suspicious Binary Name</div>
                  <div>{service.config_audit.has_suspicious_binary_name ? (
                    <Badge className="badge-destructive">Yes - Risk</Badge>
                  ) : (
                    <Badge className="badge-success">No</Badge>
                  )}</div>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Digital Signature</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <div className="text-sm font-medium">Signed</div>
                  <div>{service.signature_info.is_signed ? (
                    <Badge className="badge-success">Yes</Badge>
                  ) : (
                    <Badge className="badge-destructive">No</Badge>
                  )}</div>
                </div>
                <div className="space-y-2">
                  <div className="text-sm font-medium text-muted-foreground">Trusted</div>
                  <div>{service.signature_info.is_trusted ? (
                    <Badge className="badge-success">Yes</Badge>
                  ) : (
                    <Badge className="badge-destructive">No</Badge>
                  )}</div>
                </div>
                <div className="space-y-2">
                  <div className="text-sm font-medium text-muted-foreground">Signer</div>
                  <div className="text-sm">{service.signature_info.signer_name || 'N/A'}</div>
                </div>
                <div className="space-y-2">
                  <div className="text-sm font-medium text-muted-foreground">Issuer</div>
                  <div className="text-sm">{service.signature_info.issuer_name || 'N/A'}</div>
                </div>
                <div className="space-y-2">
                  <div className="text-sm font-medium text-muted-foreground">Timestamp</div>
                  <div className="text-sm">{service.signature_info.timestamp ? formatDate(service.signature_info.timestamp) : 'N/A'}</div>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="history" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Configuration History</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-muted-foreground text-center py-8">Configuration history tracking coming soon</p>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}

function getStatusBadge(status: string) {
  switch (status) {
    case 'RUNNING':
      return <Badge className="badge-success"><Server className="mr-1 h-3 w-3" /> Running</Badge>
    case 'STOPPED':
      return <Badge className="badge-offline"><ServerOff className="mr-1 h-3 w-3" /> Stopped</Badge>
    case 'PAUSED':
      return <Badge className="badge-stale"><Pause className="mr-1 h-3 w-3" /> Paused</Badge>
    default:
      return <Badge>{status}</Badge>
  }
}

function getStartTypeBadge(type: string) {
  const colors: Record<string, string> = {
    AUTO: 'badge-success',
    DELAYED_AUTO: 'badge-success',
    MANUAL: 'badge-stale',
    DISABLED: 'badge-offline',
  }
  return <Badge className={colors[type] || 'badge-info'}>{type}</Badge>
}

function formatDate(date: string) {
  return new Date(date).toLocaleString()
}

export default ServiceInvestigationPage
