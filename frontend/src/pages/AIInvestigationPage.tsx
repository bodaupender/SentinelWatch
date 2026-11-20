import { useState } from 'react'
import { Bot, ExternalLink, LoaderCircle, RefreshCw, ShieldAlert } from 'lucide-react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import api from '@lib/api'
import { Card, CardContent, CardHeader, CardTitle } from '@components/ui/card'
import { Badge } from '@components/ui/badge'
import { Button } from '@components/ui/button'

type Alert = { id: string; severity: string; status: string; summary: string; agent_hostname?: string | null; created_at: string }
type Report = { summary: string; findings: string[]; timeline: string[]; evidence_ids: string[]; confidence: string; recommended_steps: string[]; limitations: string[]; model: string }

export function AIInvestigationPage() {
  const [report, setReport] = useState<Report | null>(null)
  const status = useQuery({ queryKey: ['ai-status'], queryFn: async () => (await api.get('/api/v1/ai/status')).data, refetchInterval: 30_000 })
  const alerts = useQuery({ queryKey: ['ai-investigation-alerts'], queryFn: async () => (await api.get('/api/v1/alerts?limit=100&sort=created_at&order=desc')).data as { data: Alert[]; total: number }, refetchInterval: 30_000 })
  const investigate = useMutation({ mutationFn: async (id: string) => (await api.post<Report>(`/api/v1/alerts/${id}/investigate`)).data, onSuccess: setReport })
  const ai = status.data as { provider?: string; model?: string; available?: boolean; loaded?: boolean; message?: string } | undefined
  const alertRows = alerts.data?.data ?? []
  return <div className="space-y-6">
    <div><h1 className="text-3xl font-bold tracking-tight flex items-center gap-2"><Bot className="h-8 w-8 text-primary" /> AI Investigation</h1><p className="text-muted-foreground">Evidence-grounded, read-only support for alert triage. Recommendations require analyst review.</p></div>
    <Card><CardHeader><CardTitle className="flex items-center justify-between">Local AI status<Button variant="outline" size="sm" onClick={() => status.refetch()}><RefreshCw className="mr-2 h-4 w-4"/>Refresh</Button></CardTitle></CardHeader><CardContent className="flex flex-wrap items-center gap-3"><Badge variant={ai?.available ? 'default' : 'destructive'}>{ai?.available ? (ai.loaded ? 'Ready' : 'Installed') : 'Unavailable'}</Badge><span>{ai?.provider || 'ollama'} · {ai?.model || 'qwen3.5:4b'}</span><span className="text-sm text-muted-foreground">{ai?.message || 'Checking local AI service…'}</span></CardContent></Card>
    <Card><CardHeader><CardTitle>Alerts available for investigation ({alerts.data?.total ?? 0})</CardTitle></CardHeader><CardContent className="space-y-3">{alerts.isLoading ? <p>Loading alerts…</p> : alerts.error ? <p className="text-destructive">Could not load alerts: {(alerts.error as Error).message}</p> : alertRows.length === 0 ? <div className="rounded-md border p-5 text-sm text-muted-foreground">No alerts to investigate yet. The AI workspace is active; investigations become available when detection rules create alerts from endpoint telemetry.</div> : alertRows.map(alert => <div key={alert.id} className="flex flex-wrap items-center justify-between gap-3 rounded-md border p-3"><div className="min-w-0"><div className="flex items-center gap-2"><Badge>{alert.severity}</Badge><span className="font-medium truncate">{alert.summary}</span></div><p className="mt-1 text-xs text-muted-foreground">{alert.agent_hostname || 'Unknown endpoint'} · {alert.status} · {new Date(alert.created_at).toLocaleString()}</p></div><div className="flex gap-2"><Button variant="outline" size="sm" asChild><Link to={`/alert/${alert.id}`}><ExternalLink className="mr-2 h-4 w-4"/>Details</Link></Button><Button size="sm" onClick={() => { setReport(null); investigate.mutate(alert.id) }} disabled={investigate.isPending || !ai?.available}>{investigate.isPending ? <LoaderCircle className="mr-2 h-4 w-4 animate-spin"/> : <Bot className="mr-2 h-4 w-4"/>}Investigate</Button></div></div>)}</CardContent></Card>
    {investigate.error && <p className="text-sm text-destructive">Investigation failed: {(investigate.error as Error).message}</p>}
    {report && <Card><CardHeader><CardTitle>Investigation report · {report.model} · {report.confidence} confidence</CardTitle></CardHeader><CardContent className="space-y-4"><p>{report.summary}</p>{[['Findings', report.findings], ['Timeline', report.timeline], ['Recommended steps', report.recommended_steps], ['Limitations', report.limitations]].map(([heading, rows]) => <section key={heading as string}><h3 className="font-semibold">{heading}</h3><ul className="list-disc pl-5 text-sm">{(rows as string[]).map((row, i) => <li key={i}>{row}</li>)}</ul></section>)}<div className="text-xs text-muted-foreground flex gap-2"><ShieldAlert className="h-4 w-4"/>Evidence records cited: {report.evidence_ids.length ? report.evidence_ids.join(', ') : 'none'}</div></CardContent></Card>}
  </div>
}
