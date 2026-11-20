import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs))
}

export function formatDate(date: string | Date, options?: Intl.DateTimeFormatOptions): string {
  const value = new Date(date)
  return value.toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    ...options,
  })
}

export function formatRelativeTime(date: string | Date): string {
  const seconds = Math.floor((Date.now() - new Date(date).getTime()) / 1000)
  if (seconds < 60) return 'just now'
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  if (days < 7) return `${days}d ago`
  return formatDate(date)
}

export function getSeverityClass(severity: string): string {
  switch (severity.toLowerCase()) {
    case 'critical': return 'badge-critical'
    case 'high': return 'badge-high'
    case 'medium': return 'badge-medium'
    case 'low': return 'badge-low'
    default: return 'badge-info'
  }
}

export function getStatusClass(status: string): string {
  switch (status.toLowerCase()) {
    case 'online': return 'badge-online'
    case 'offline': return 'badge-offline'
    case 'stale': return 'badge-stale'
    case 'new':
    case 'investigating': return 'badge-high'
    case 'true_positive':
    case 'resolved': return 'badge-success'
    case 'false_positive':
    case 'benign': return 'badge-low'
    default: return 'badge-info'
  }
}

export function truncate(value: string, length: number): string {
  return value.length <= length ? value : `${value.slice(0, length - 3)}...`
}

export function debounce<T extends (...args: any[]) => void>(fn: T, delay: number): (...args: Parameters<T>) => void {
  let timeoutId: ReturnType<typeof setTimeout>
  return (...args) => {
    clearTimeout(timeoutId)
    timeoutId = setTimeout(() => fn(...args), delay)
  }
}

export function classNames(...classes: Array<string | boolean | null | undefined>): string {
  return classes.filter(Boolean).join(' ')
}
