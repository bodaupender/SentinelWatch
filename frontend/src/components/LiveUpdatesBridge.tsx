import { useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useAuthStore } from '@hooks/useAuthStore'

const API_BASE_URL = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '')

/**
 * Consume tenant-scoped SSE invalidation notices. Screens keep their existing
 * refetch intervals as a fallback when streaming is unavailable.
 */
export function LiveUpdatesBridge() {
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated)
  const accessToken = useAuthStore((state) => state.accessToken)
  const organizationId = useAuthStore((state) => state.selectedOrganizationId)
  const queryClient = useQueryClient()

  useEffect(() => {
    if (!isAuthenticated || !accessToken) return

    let stopped = false
    let controller: AbortController | undefined
    let retryTimer: number | undefined
    let retryDelay = 1000

    const waitForRetry = (milliseconds: number) => new Promise<void>((resolve) => {
      retryTimer = window.setTimeout(resolve, milliseconds)
    })

    const connect = async () => {
      while (!stopped) {
        const latestToken = useAuthStore.getState().accessToken
        if (!latestToken || !useAuthStore.getState().isAuthenticated) return

        controller = new AbortController()
        try {
          const headers = new Headers({ Authorization: `Bearer ${latestToken}` })
          if (organizationId) headers.set('X-Organization-ID', organizationId)
          const response = await fetch(`${API_BASE_URL}/api/v1/events/stream`, {
            method: 'GET',
            headers,
            credentials: 'include',
            signal: controller.signal,
          })

          if (response.status === 401) {
            await useAuthStore.getState().refreshAccessToken()
            retryDelay = 1000
            continue
          }
          if (!response.ok || !response.body) throw new Error('Live update stream unavailable')

          retryDelay = 1000
          const reader = response.body.getReader()
          const decoder = new TextDecoder()
          let buffer = ''
          try {
            while (!stopped) {
              const { done, value } = await reader.read()
              if (done) break
              buffer += decoder.decode(value, { stream: true })
              const frames = buffer.split(/\r?\n\r?\n/)
              buffer = frames.pop() ?? ''
              for (const frame of frames) {
                if (/^event: (ready|invalidate)$/m.test(frame)) {
                  void queryClient.invalidateQueries()
                }
              }
            }
          } finally {
            await reader.cancel().catch(() => undefined)
          }
        } catch {
          if (stopped || controller.signal.aborted) return
          // Existing React Query polling continues while the stream reconnects.
        }

        if (stopped) return
        const jitter = Math.floor(Math.random() * Math.max(100, retryDelay / 4))
        await waitForRetry(retryDelay + jitter)
        retryDelay = Math.min(retryDelay * 2, 30_000)
      }
    }

    void connect()
    return () => {
      stopped = true
      controller?.abort()
      if (retryTimer !== undefined) window.clearTimeout(retryTimer)
    }
  }, [accessToken, isAuthenticated, organizationId, queryClient])

  return null
}
