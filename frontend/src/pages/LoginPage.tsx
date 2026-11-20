import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Shield, Loader2, Eye, EyeOff } from 'lucide-react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { toast } from 'sonner'
import { useAuthStore } from '@hooks/useAuthStore'
import { authApi } from '@lib/api'
import { Button } from '@components/ui/button'
import { Input } from '@components/ui/input'
import { Label } from '@components/ui/label'
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@components/ui/card'

const loginSchema = z.object({
  username: z.string().min(1, 'Username is required'),
  password: z.string().min(1, 'Password is required'),
  mfaCode: z.string().optional(),
})

const registrationSchema = z.object({
  username: z.string().min(3, 'Use at least 3 characters').max(64).regex(/^[A-Za-z0-9_.-]+$/, 'Use letters, numbers, dots, dashes, or underscores'),
  email: z.string().email('Enter a valid email address'),
  fullName: z.string().max(255).optional(),
  password: z.string().min(12, 'Use at least 12 characters').max(128),
})

type LoginForm = z.infer<typeof loginSchema>
type RegistrationForm = z.infer<typeof registrationSchema>

export function LoginPage() {
  const navigate = useNavigate()
  const { login, isLoading } = useAuthStore()
  const [showPassword, setShowPassword] = useState(false)
  const [showMFA, setShowMFA] = useState(false)
  const [isSigningUp, setIsSigningUp] = useState(false)
  const [mode, setMode] = useState<'signin' | 'signup'>('signin')

  const loginForm = useForm<LoginForm>({
    resolver: zodResolver(loginSchema),
    defaultValues: { username: '', password: '', mfaCode: '' },
  })
  const registrationForm = useForm<RegistrationForm>({
    resolver: zodResolver(registrationSchema),
    defaultValues: { username: '', email: '', fullName: '', password: '' },
  })

  const onLogin = async (data: LoginForm) => {
    try {
      await login(data.username, data.password, data.mfaCode || undefined)
      toast.success('Welcome back!')
      navigate('/')
    } catch (error: unknown) {
      const axiosError = error as { response?: { data?: { detail?: string; mfa_required?: boolean } } }
      if (axiosError.response?.data?.mfa_required) {
        setShowMFA(true)
        toast.info('MFA code required')
      } else {
        toast.error(axiosError.response?.data?.detail || 'Login failed')
      }
    }
  }

  const onRegister = async (data: RegistrationForm) => {
    setIsSigningUp(true)
    try {
      await authApi.register({
        username: data.username,
        email: data.email,
        full_name: data.fullName?.trim() || undefined,
        password: data.password,
      })
      loginForm.setValue('username', data.username)
      loginForm.setValue('password', '')
      registrationForm.reset()
      setMode('signin')
      toast.success('Account created. Sign in with your new credentials.')
    } catch (error: unknown) {
      const axiosError = error as { response?: { data?: { detail?: string } } }
      toast.error(axiosError.response?.data?.detail || 'Could not create account')
    } finally {
      setIsSigningUp(false)
    }
  }

  const busy = isLoading || isSigningUp
  const registrationErrors = registrationForm.formState.errors

  return (
    <div className="flex min-h-screen items-center justify-center bg-muted/50 px-4">
      <Card className="w-full max-w-md">
        <CardHeader className="text-center">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-primary/10">
            <Shield className="h-7 w-7 text-primary" />
          </div>
          <CardTitle className="text-2xl">
            {mode === 'signin' ? 'Sign in to SentinelWatch' : 'Create your SentinelWatch account'}
          </CardTitle>
          <CardDescription>
            {mode === 'signin'
              ? 'Enter your credentials to access the SOC dashboard'
              : 'Create an analyst account to access the SOC dashboard'}
          </CardDescription>
        </CardHeader>

        <CardContent>
          {mode === 'signin' ? (
            <form id="auth-form" onSubmit={loginForm.handleSubmit(onLogin)} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="username">Username</Label>
                <Input id="username" autoComplete="username" placeholder="Enter your username" {...loginForm.register('username')} disabled={busy} aria-invalid={!!loginForm.formState.errors.username} />
                {loginForm.formState.errors.username && <p className="text-sm text-destructive">{loginForm.formState.errors.username.message}</p>}
              </div>

              <div className="space-y-2">
                <Label htmlFor="password">Password</Label>
                <div className="relative">
                  <Input id="password" type={showPassword ? 'text' : 'password'} autoComplete="current-password" placeholder="Enter your password" {...loginForm.register('password')} disabled={busy} aria-invalid={!!loginForm.formState.errors.password} />
                  <button type="button" onClick={() => setShowPassword(!showPassword)} className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground" aria-label={showPassword ? 'Hide password' : 'Show password'}>
                    {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
                {loginForm.formState.errors.password && <p className="text-sm text-destructive">{loginForm.formState.errors.password.message}</p>}
              </div>

              {showMFA && (
                <div className="space-y-2">
                  <Label htmlFor="mfaCode">MFA Code</Label>
                  <Input id="mfaCode" type="text" placeholder="Enter 6-digit code" maxLength={6} {...loginForm.register('mfaCode')} disabled={busy} autoComplete="one-time-code" aria-invalid={!!loginForm.formState.errors.mfaCode} />
                </div>
              )}
            </form>
          ) : (
            <form id="auth-form" onSubmit={registrationForm.handleSubmit(onRegister)} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="signup-username">Username</Label>
                <Input id="signup-username" autoComplete="username" placeholder="Choose a username" {...registrationForm.register('username')} disabled={busy} aria-invalid={!!registrationErrors.username} />
                {registrationErrors.username && <p className="text-sm text-destructive">{registrationErrors.username.message}</p>}
              </div>
              <div className="space-y-2">
                <Label htmlFor="signup-email">Email</Label>
                <Input id="signup-email" type="email" autoComplete="email" placeholder="you@example.com" {...registrationForm.register('email')} disabled={busy} aria-invalid={!!registrationErrors.email} />
                {registrationErrors.email && <p className="text-sm text-destructive">{registrationErrors.email.message}</p>}
              </div>
              <div className="space-y-2">
                <Label htmlFor="signup-full-name">Full name (optional)</Label>
                <Input id="signup-full-name" autoComplete="name" placeholder="Your name" {...registrationForm.register('fullName')} disabled={busy} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="signup-password">Password</Label>
                <div className="relative">
                  <Input id="signup-password" type={showPassword ? 'text' : 'password'} autoComplete="new-password" placeholder="At least 12 characters" {...registrationForm.register('password')} disabled={busy} aria-invalid={!!registrationErrors.password} />
                  <button type="button" onClick={() => setShowPassword(!showPassword)} className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground" aria-label={showPassword ? 'Hide password' : 'Show password'}>
                    {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
                {registrationErrors.password && <p className="text-sm text-destructive">{registrationErrors.password.message}</p>}
              </div>
              <p className="text-xs text-muted-foreground">New accounts receive analyst access. Administrator access cannot be selected here.</p>
            </form>
          )}
        </CardContent>

        <CardFooter className="flex flex-col space-y-4">
          <Button type="submit" className="w-full" form="auth-form" disabled={busy}>
            {busy ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />{mode === 'signin' ? 'Signing in...' : 'Creating account...'}</> : mode === 'signin' ? 'Sign in' : 'Create account'}
          </Button>
          <p className="text-center text-sm text-muted-foreground">
            {mode === 'signin' ? 'New to SentinelWatch? ' : 'Already have an account? '}
            <button type="button" className="font-medium text-primary underline-offset-4 hover:underline" onClick={() => setMode(mode === 'signin' ? 'signup' : 'signin')} disabled={busy}>
              {mode === 'signin' ? 'Create an account' : 'Sign in'}
            </button>
          </p>
        </CardFooter>
      </Card>
    </div>
  )
}
