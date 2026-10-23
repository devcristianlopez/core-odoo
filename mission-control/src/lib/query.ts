import { QueryClient } from '@tanstack/react-query'

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 10_000,
      retry: (failureCount, error) => {
        const status = (error as { status?: number } | null)?.status
        if (status && status >= 400 && status < 500) return false
        return failureCount < 2
      },
      refetchOnWindowFocus: false,
    },
    mutations: {
      retry: false,
    },
  },
})

export const queryKeys = {
  status: ['status'] as const,
  health: ['health'] as const,
  me: ['me'] as const,
  projects: ['projects'] as const,
  project: (name: string) => ['projects', name] as const,
  environments: (name: string) => ['projects', name, 'environments'] as const,
  iterations: (name: string) => ['projects', name, 'iterations'] as const,
  logs: (name: string, stage: string, tail: number) =>
    ['projects', name, 'environments', stage, 'logs', tail] as const,
  metrics: (query: string) => ['metrics', query] as const,
  audit: (limit: number) => ['audit', limit] as const,
  users: ['users'] as const,
}
