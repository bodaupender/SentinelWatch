import { User, Shield, Bell, Palette, Server, UserPlus, Moon, Sun, Monitor, Copy } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@components/ui/card'
import { Button } from '@components/ui/button'
import { Input } from '@components/ui/input'
import { Label } from '@components/ui/label'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@components/ui/tabs'
import { Switch } from '@components/ui/switch'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@components/ui/select'
import { useAuthStore } from '@hooks/useAuthStore'
import { useThemeStore } from '@hooks/useThemeStore'
import { authApi } from '@lib/api'
import { toast } from 'sonner'

type NotificationPrefs = { email: boolean; push: boolean; alerts: boolean }

export function SettingsPage() {
  const { user } = useAuthStore()
  const checkAuth = useAuthStore((state) => state.checkAuth)
  const { theme, setTheme } = useThemeStore()
  const [activeTab, setActiveTab] = useState('profile')
  const [mfaSetup, setMfaSetup] = useState<{ secret: string; otpauth_url: string } | null>(null)
  const [mfaCode, setMfaCode] = useState('')
  const [passwordForm, setPasswordForm] = useState({ current: '', next: '' })
  const [busyAction, setBusyAction] = useState(false)
  const [profile, setProfile] = useState({ email: user?.email || '', full_name: user?.full_name || '' })
  const [notifications, setNotifications] = useState<NotificationPrefs>(() => {
    const defaults = { email: true, push: false, alerts: true }
    try {
      return { ...defaults, ...(JSON.parse(localStorage.getItem('sentinelwatch-notifications') || '{}')) }
    } catch {
      return defaults
    }
  })

  useEffect(() => setProfile({ email: user?.email || '', full_name: user?.full_name || '' }), [user])

  const saveProfile = useMutation({
    mutationFn: () => authApi.updateProfile(profile),
    onSuccess: async () => {
      await checkAuth()
      toast.success('Profile updated')
    },
    onError: (error: any) => toast.error(error.response?.data?.detail || 'Could not update profile'),
  })

  const startMfa = async () => { setBusyAction(true); try { const result = await authApi.mfaSetup(); setMfaSetup(result.data); toast.success('Scan the secret in your authenticator app, then verify a code') } catch (e: any) { toast.error(e.response?.data?.detail || 'Could not start two-factor setup') } finally { setBusyAction(false) } }
  const verifyMfa = async () => { setBusyAction(true); try { await authApi.mfaVerify(mfaCode); setMfaSetup(null); setMfaCode(''); await checkAuth(); toast.success('Two-factor authentication enabled') } catch (e: any) { toast.error(e.response?.data?.detail || 'Code verification failed') } finally { setBusyAction(false) } }
  const disableMfa = async () => { setBusyAction(true); try { await authApi.mfaDisable(mfaCode); setMfaCode(''); await checkAuth(); toast.success('Two-factor authentication disabled') } catch (e: any) { toast.error(e.response?.data?.detail || 'Code verification failed') } finally { setBusyAction(false) } }
  const changePassword = async () => { setBusyAction(true); try { await authApi.changePassword(passwordForm.current, passwordForm.next); setPasswordForm({ current: '', next: '' }); toast.success('Password changed. Sign in again because active sessions were revoked.') } catch (e: any) { toast.error(e.response?.data?.detail || 'Could not change password') } finally { setBusyAction(false) } }

  const updateNotification = (key: keyof NotificationPrefs, value: boolean) => {
    setNotifications((current) => {
      const next = { ...current, [key]: value }
      localStorage.setItem('sentinelwatch-notifications', JSON.stringify(next))
      return next
    })
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Settings</h1>
        <p className="text-muted-foreground">Manage your account and preferences</p>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
        <TabsList className="grid w-full grid-cols-5">
          <TabsTrigger value="profile"><User className="mr-2 h-4 w-4" /> Profile</TabsTrigger>
          <TabsTrigger value="appearance"><Palette className="mr-2 h-4 w-4" /> Appearance</TabsTrigger>
          <TabsTrigger value="notifications"><Bell className="mr-2 h-4 w-4" /> Notifications</TabsTrigger>
          <TabsTrigger value="security"><Shield className="mr-2 h-4 w-4" /> Security</TabsTrigger>
          {user?.role === 'admin' && <TabsTrigger value="admin"><Server className="mr-2 h-4 w-4" /> Admin</TabsTrigger>}
        </TabsList>

        <TabsContent value="profile" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Profile Information</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="fullName">Full Name</Label>
                  <Input id="fullName" value={profile.full_name} onChange={(event) => setProfile({ ...profile, full_name: event.target.value })} />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="username">Username</Label>
                  <Input id="username" defaultValue={user?.username || ''} disabled />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="email">Email</Label>
                  <Input id="email" type="email" value={profile.email} onChange={(event) => setProfile({ ...profile, email: event.target.value })} />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="role">Role</Label>
                  <Input id="role" defaultValue={user?.role || ''} disabled />
                </div>
              </div>
              <Button onClick={() => saveProfile.mutate()} disabled={saveProfile.isPending || !profile.email.trim()}>{saveProfile.isPending ? 'Saving…' : 'Save Changes'}</Button>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="appearance" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Theme</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center justify-between">
                <div className="space-y-1">
                  <p className="font-medium">Light</p>
                  <p className="text-sm text-muted-foreground">Always use light mode</p>
                </div>
                <Button
                  variant={theme === 'light' ? 'default' : 'outline'}
                  onClick={() => setTheme('light')}
                >
                  <Sun className="mr-2 h-4 w-4" />
                  Light
                </Button>
              </div>
              <div className="flex items-center justify-between">
                <div className="space-y-1">
                  <p className="font-medium">Dark</p>
                  <p className="text-sm text-muted-foreground">Always use dark mode</p>
                </div>
                <Button
                  variant={theme === 'dark' ? 'default' : 'outline'}
                  onClick={() => setTheme('dark')}
                >
                  <Moon className="mr-2 h-4 w-4" />
                  Dark
                </Button>
              </div>
              <div className="flex items-center justify-between">
                <div className="space-y-1">
                  <p className="font-medium">System</p>
                  <p className="text-sm text-muted-foreground">Match system preference</p>
                </div>
                <Button
                  variant={theme === 'system' ? 'default' : 'outline'}
                  onClick={() => setTheme('system')}
                >
                  <Monitor className="mr-2 h-4 w-4" />
                  System
                </Button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="notifications" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Notification Preferences</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center justify-between">
                <div className="space-y-1">
                  <p className="font-medium">Email Notifications</p>
                  <p className="text-sm text-muted-foreground">Receive email alerts</p>
                </div>
                <Switch checked={notifications.email} onCheckedChange={(c) => updateNotification('email', c)} />
              </div>
              <div className="flex items-center justify-between">
                <div className="space-y-1">
                  <p className="font-medium">Push Notifications</p>
                  <p className="text-sm text-muted-foreground">Browser push notifications</p>
                </div>
                <Switch checked={notifications.push} onCheckedChange={(c) => updateNotification('push', c)} />
              </div>
              <div className="flex items-center justify-between">
                <div className="space-y-1">
                  <p className="font-medium">Alert Notifications</p>
                  <p className="text-sm text-muted-foreground">Real-time alert notifications</p>
                </div>
                <Switch checked={notifications.alerts} onCheckedChange={(c) => updateNotification('alerts', c)} />
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="security" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Security</CardTitle>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="flex items-center justify-between border-b pb-6">
                <div className="space-y-1">
                  <p className="font-medium">Two-Factor Authentication</p>
                  <p className="text-sm text-muted-foreground">Add an extra layer of security</p>
                </div>
                <Button variant="outline" disabled={busyAction} onClick={() => user?.mfa_enabled ? setMfaSetup({ secret: '', otpauth_url: '' }) : startMfa()}>{user?.mfa_enabled ? 'Disable 2FA' : 'Enable 2FA'}</Button>
              </div>
              {(mfaSetup || user?.mfa_enabled) && <div className="space-y-3 rounded-md border p-4"><p className="text-sm">{user?.mfa_enabled ? 'Enter a current authenticator code to disable 2FA.' : 'Add this secret to an authenticator app, then enter its current six-digit code.'}</p>{mfaSetup?.secret && <div className="space-y-2"><Label>Authenticator secret</Label><div className="flex gap-2"><Input readOnly value={mfaSetup.secret}/><Button type="button" variant="outline" size="icon" onClick={() => { navigator.clipboard.writeText(mfaSetup.secret); toast.success('Secret copied') }}><Copy className="h-4 w-4"/></Button></div><a className="text-sm underline" href={mfaSetup.otpauth_url}>Open authenticator link</a></div>}<div className="flex gap-2"><Input aria-label="Authenticator code" inputMode="numeric" maxLength={6} placeholder="6-digit code" value={mfaCode} onChange={e => setMfaCode(e.target.value.replace(/\D/g, ''))}/><Button disabled={busyAction || mfaCode.length !== 6} onClick={user?.mfa_enabled ? disableMfa : verifyMfa}>{user?.mfa_enabled ? 'Verify and disable' : 'Verify and enable'}</Button><Button variant="ghost" onClick={() => { setMfaSetup(null); setMfaCode('') }}>Cancel</Button></div></div>}
              <div className="flex items-center justify-between border-b pb-6">
                <div className="space-y-1">
                  <p className="font-medium">Change Password</p>
                  <p className="text-sm text-muted-foreground">Update your password</p>
                </div>
                <Button variant="outline" onClick={() => document.getElementById('password-change')?.scrollIntoView({ behavior: 'smooth' })}>Change Password</Button>
              </div>
              <div id="password-change" className="space-y-3 rounded-md border p-4"><Label htmlFor="current-password">Current password</Label><Input id="current-password" type="password" autoComplete="current-password" value={passwordForm.current} onChange={e => setPasswordForm({ ...passwordForm, current: e.target.value })}/><Label htmlFor="new-password">New password (at least 12 characters)</Label><Input id="new-password" type="password" autoComplete="new-password" minLength={12} value={passwordForm.next} onChange={e => setPasswordForm({ ...passwordForm, next: e.target.value })}/><Button disabled={busyAction || !passwordForm.current || passwordForm.next.length < 12} onClick={changePassword}>Update Password</Button></div>
              <div className="flex items-center justify-between">
                <div className="space-y-1">
                  <p className="font-medium">API Keys</p>
                  <p className="text-sm text-muted-foreground">Manage API access tokens</p>
                </div>
                <Button variant="outline" disabled title="API key management is not enabled in this build">API key management unavailable</Button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {user?.role === 'admin' && (
          <TabsContent value="admin" className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle>Administration</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex items-center justify-between border-b pb-4">
                  <div className="space-y-1">
                    <p className="font-medium">User Management</p>
                    <p className="text-sm text-muted-foreground">Manage user accounts and roles</p>
                  </div>
                  <Button>
                    <UserPlus className="mr-2 h-4 w-4" />
                    Add User
                  </Button>
                </div>
                <div className="flex items-center justify-between border-b pb-4">
                  <div className="space-y-1">
                    <p className="font-medium">Agent Enrollment</p>
                    <p className="text-sm text-muted-foreground">Generate enrollment tokens</p>
                  </div>
                  <Button variant="outline">Generate Token</Button>
                </div>
                <div className="flex items-center justify-between">
                  <div className="space-y-1">
                    <p className="font-medium">System Configuration</p>
                    <p className="text-sm text-muted-foreground">Global system settings</p>
                  </div>
                  <Button variant="outline">Configure</Button>
                </div>
              </CardContent>
            </Card>
          </TabsContent>
        )}
      </Tabs>
    </div>
  )
}

export default SettingsPage
