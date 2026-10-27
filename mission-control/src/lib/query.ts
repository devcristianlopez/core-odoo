import { QueryClient, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from './api'

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
  members: (name: string) => ['projects', name, 'members'] as const,
  access: (name: string) => ['projects', name, 'access'] as const,
  logs: (name: string, stage: string, tail: number) =>
    ['projects', name, 'environments', stage, 'logs', tail] as const,
  metrics: (query: string) => ['metrics', query] as const,
  audit: (limit: number) => ['audit', limit] as const,
  users: ['users'] as const,
  approvals: (status?: string) => ['approvals', status ?? 'all'] as const,
}

export interface RollbackVariables {
  stage: string
  /** Required on prod: must match the project name exactly. */
  confirm?: string
}

/**
 * Rolls an environment back to its last good iteration. Shares the
 * post-mutation invalidation used by the other environment actions so the
 * environment detail, project detail and project list all refresh.
 */
export function useRollbackEnvironment(project: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ stage, confirm }: RollbackVariables) =>
      api.environments.rollbackEnvironment(project, stage, confirm),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.project(project) })
      void queryClient.invalidateQueries({ queryKey: queryKeys.environments(project) })
      void queryClient.invalidateQueries({ queryKey: queryKeys.projects })
      void queryClient.invalidateQueries({ queryKey: queryKeys.status })
      void queryClient.invalidateQueries({ queryKey: ['audit'] })
    },
  })
}
