import { useState, type ReactElement } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Plus, UserMinus, Users } from 'lucide-react'
import { api } from '../../lib/api'
import { queryKeys } from '../../lib/query'
import { useToast } from '../../lib/toast-context'
import { describeError } from '../../lib/errors'
import { Card, CardContent, CardHeader } from '../ui/Card'
import { Button } from '../ui/Button'
import { Badge } from '../ui/Badge'
import { Input, Select } from '../ui/Input'
import { EmptyState } from '../ui/EmptyState'
import { ErrorState } from '../ui/ErrorState'
import { LoadingState } from '../ui/Loading'

export function MembersPanel({ project, canManage }: { project: string; canManage: boolean }): ReactElement {
  const { t } = useTranslation()
  const { pushToast } = useToast()
  const queryClient = useQueryClient()
  const [username, setUsername] = useState('')
  const [role, setRole] = useState<'owner' | 'developer' | 'viewer'>('developer')

  const membersQuery = useQuery({
    queryKey: queryKeys.members(project),
    queryFn: () => api.members.list(project),
    enabled: canManage,
  })

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.members(project) })
    void queryClient.invalidateQueries({ queryKey: queryKeys.projects })
    void queryClient.invalidateQueries({ queryKey: ['audit'] })
  }

  const addMutation = useMutation({
    mutationFn: ({ name, role }: { name: string; role: 'owner' | 'developer' | 'viewer' }) =>
      api.members.add(project, name, role),
    onSuccess: (member) => {
      setUsername('')
      setRole('developer')
      refresh()
      pushToast({ title: t('members.added', { username: member.username }), variant: 'success' })
    },
    onError: (error) => {
      pushToast({ title: t('members.addFailed'), description: describeError(error, t), variant: 'error' })
    },
  })

  const updateRoleMutation = useMutation({
    mutationFn: ({ name, role }: { name: string; role: string }) =>
      api.members.update(project, name, role),
    onSuccess: () => refresh(),
    onError: (error) => {
      pushToast({ title: t('members.updateFailed'), description: describeError(error, t), variant: 'error' })
    },
  })

  const removeMutation = useMutation({
    mutationFn: (name: string) => api.members.remove(project, name),
    onSuccess: (_result, name) => {
      refresh()
      pushToast({ title: t('members.removed', { username: name }), variant: 'success' })
    },
    onError: (error) => {
      pushToast({ title: t('members.removeFailed'), description: describeError(error, t), variant: 'error' })
    },
  })

  if (!canManage) return <></>

  return (
    <Card>
      <CardHeader
        title={t('members.title')}
        description={t('members.subtitle')}
        actions={
          <form
            className="flex items-center gap-1.5"
            onSubmit={(event) => {
              event.preventDefault()
              if (username.trim()) addMutation.mutate({ name: username.trim(), role })
            }}
          >
            <Input
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              placeholder={t('members.addPlaceholder')}
              className="h-9 w-32"
              aria-label={t('members.addPlaceholder')}
            />
            <Select
              value={role}
              onChange={(event) => setRole(event.target.value as 'owner' | 'developer' | 'viewer')}
              className="h-9 w-32"
              aria-label={t('members.role')}
            >
              {(['owner', 'developer', 'viewer'] as const).map((value) => (
                <option key={value} value={value}>{t(`members.${value}`)}</option>
              ))}
            </Select>
            <Button type="submit" size="sm" variant="primary" disabled={addMutation.isPending}>
              <Plus className="h-3.5 w-3.5" aria-hidden="true" />
              {t('members.add')}
            </Button>
          </form>
        }
      />
      {membersQuery.isLoading ? (
        <CardContent><LoadingState rows={2} /></CardContent>
      ) : membersQuery.isError ? (
        <CardContent><ErrorState error={membersQuery.error} onRetry={() => void membersQuery.refetch()} /></CardContent>
      ) : (membersQuery.data ?? []).length === 0 ? (
        <CardContent>
          <EmptyState icon={Users} title={t('members.title')} description={t('members.empty')} />
        </CardContent>
      ) : (
        <ul className="divide-y divide-edge-muted">
          {(membersQuery.data ?? []).map((member) => (
            <li key={member.username} className="flex items-center justify-between gap-3 px-5 py-3">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-slate-100">{member.username}</span>
                <Select
                  value={member.role}
                  onChange={(event) => updateRoleMutation.mutate({ name: member.username, role: event.target.value })}
                  className="h-8 w-28"
                  aria-label={t('members.role')}
                >
                  {(['owner', 'developer', 'viewer'] as const).map((value) => (
                    <option key={value} value={value}>{t(`members.${value}`)}</option>
                  ))}
                </Select>
                <Badge tone="neutral">{member.user_role}</Badge>
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => removeMutation.mutate(member.username)}
                disabled={removeMutation.isPending}
              >
                <UserMinus className="h-3.5 w-3.5" aria-hidden="true" />
                {t('members.remove')}
              </Button>
            </li>
          ))}
        </ul>
      )}
      <CardContent className="border-t border-edge-muted pt-3">
        <p className="text-[11px] text-slate-500">{t('members.hint')}</p>
      </CardContent>
    </Card>
  )
}
