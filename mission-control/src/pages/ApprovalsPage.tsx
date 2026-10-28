import { useState, type ReactElement } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { CheckCheck, Check, X } from 'lucide-react'
import { api } from '../lib/api'
import { queryKeys } from '../lib/query'
import type { DeploymentRequest } from '../lib/types'
import { useAuth } from '../lib/auth-context'
import { useToast } from '../lib/toast-context'
import { formatDate } from '../lib/format'
import { describeError } from '../lib/errors'
import { PageHeader } from '../components/ui/PageHeader'
import { Card, CardContent, CardHeader } from '../components/ui/Card'
import { Button } from '../components/ui/Button'
import { Badge } from '../components/ui/Badge'
import { Select } from '../components/ui/Input'
import { EmptyState } from '../components/ui/EmptyState'
import { ErrorState } from '../components/ui/ErrorState'
import { LoadingState } from '../components/ui/Loading'

export default function ApprovalsPage(): ReactElement {
  const { t, i18n } = useTranslation()
  const language = i18n.resolvedLanguage ?? i18n.language
  const { user } = useAuth()
  const { pushToast } = useToast()
  const queryClient = useQueryClient()
  const [status, setStatus] = useState('pending')
  const isAdmin = user?.role === 'admin'
  const isViewer = user?.role === 'viewer'

  const requestsQuery = useQuery({
    queryKey: queryKeys.approvals(status),
    queryFn: () => api.approvals.list(status || undefined),
    enabled: !isViewer,
  })

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ['approvals'] })
    void queryClient.invalidateQueries({ queryKey: ['audit'] })
    void queryClient.invalidateQueries({ queryKey: ['projects'] })
  }

  const approveMutation = useMutation({
    mutationFn: (request: DeploymentRequest) => api.approvals.approve(request.id),
    onSuccess: (request) => {
      refresh()
      pushToast({ title: t('approvals.approved', { id: request.id }), variant: 'success' })
    },
    onError: (error) => {
      pushToast({ title: t('approvals.approveFailed'), description: describeError(error, t), variant: 'error' })
    },
  })

  const rejectMutation = useMutation({
    mutationFn: (request: DeploymentRequest) => api.approvals.reject(request.id),
    onSuccess: (request) => {
      refresh()
      pushToast({ title: t('approvals.rejected', { id: request.id }), variant: 'success' })
    },
    onError: (error) => {
      pushToast({ title: t('approvals.rejectFailed'), description: describeError(error, t), variant: 'error' })
    },
  })

  const requests = requestsQuery.data ?? []

  return (
    <>
      <PageHeader title={t('approvals.title')} description={t('approvals.subtitle')} />

      <Card>
        <CardHeader
          title={t('approvals.title')}
          description={t('approvals.subtitle')}
          actions={
            <Select value={status} onChange={(event) => setStatus(event.target.value)} className="w-40">
              <option value="pending">{t('approvals.pending')}</option>
              <option value="deployed">{t('approvals.deployed')}</option>
              <option value="rejected">{t('approvals.rejectedStatus')}</option>
              <option value="">{t('common.all')}</option>
            </Select>
          }
        />
        {isViewer ? (
          <CardContent><EmptyState icon={CheckCheck} title={t('approvals.title')} description={t('approvals.noAccess')} /></CardContent>
        ) : requestsQuery.isLoading ? (
          <CardContent><LoadingState rows={3} /></CardContent>
        ) : requestsQuery.isError ? (
          <CardContent><ErrorState error={requestsQuery.error} onRetry={() => void requestsQuery.refetch()} /></CardContent>
        ) : requests.length === 0 ? (
          <CardContent><EmptyState icon={CheckCheck} title={t('approvals.empty')} description={t('approvals.emptyHint')} /></CardContent>
        ) : (
          <ul className="divide-y divide-edge-muted">
            {requests.map((request) => (
              <li key={request.id} className="flex flex-col gap-3 px-5 py-4 sm:flex-row sm:items-start sm:justify-between">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone="neutral">#{request.id}</Badge>
                    <span className="text-sm font-semibold text-slate-100">{request.project}</span>
                    <Badge tone="info">v{request.iteration}</Badge>
                    <Badge tone={request.status === 'deployed' ? 'success' : request.status === 'rejected' ? 'danger' : 'warning'}>
                      {request.status}
                    </Badge>
                  </div>
                  <p className="mt-1 text-xs text-slate-400">
                    {t('approvals.requestedBy', { user: request.requested_by, date: formatDate(request.created_at, language) })}
                  </p>
                  {request.reason ? <p className="mt-1 text-xs text-slate-400">{request.reason}</p> : null}
                </div>
                {isAdmin && request.status === 'pending' ? (
                  <div className="flex shrink-0 gap-1.5">
                    <Button variant="primary" size="sm" onClick={() => approveMutation.mutate(request)} loading={approveMutation.isPending}>
                      <Check className="h-3.5 w-3.5" aria-hidden="true" />
                      {t('approvals.approve')}
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => rejectMutation.mutate(request)} disabled={rejectMutation.isPending}>
                      <X className="h-3.5 w-3.5" aria-hidden="true" />
                      {t('approvals.reject')}
                    </Button>
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </>
  )
}
