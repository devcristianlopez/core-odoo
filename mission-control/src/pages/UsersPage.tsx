import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Plus, ShieldCheck, UserRound } from 'lucide-react'
import { api, type CreateUserInput, type UpdateUserInput } from '../lib/api'
import { queryKeys } from '../lib/query'
import type { User, UserRole } from '../lib/types'
import { useAuth } from '../lib/auth-context'
import { useToast } from '../lib/toast-context'
import { formatDate } from '../lib/format'
import { describeError } from '../lib/errors'
import { PageHeader } from '../components/ui/PageHeader'
import { Card, CardContent, CardHeader } from '../components/ui/Card'
import { Button } from '../components/ui/Button'
import { Badge } from '../components/ui/Badge'
import { Input, Label, Select, FieldHint, FieldError } from '../components/ui/Input'
import { Modal } from '../components/ui/Modal'
import { EmptyState } from '../components/ui/EmptyState'
import { ErrorState } from '../components/ui/ErrorState'
import { LoadingState } from '../components/ui/Loading'

export default function UsersPage(): JSX.Element {
  const { t, i18n } = useTranslation()
  const language = i18n.resolvedLanguage ?? i18n.language
  const { user } = useAuth()
  const { pushToast } = useToast()
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState<UserRole>('operator')

  const isAdmin = user?.role === 'admin'
  const usersQuery = useQuery({
    queryKey: queryKeys.users,
    queryFn: () => api.users.list(),
    enabled: isAdmin,
  })

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.users })
    void queryClient.invalidateQueries({ queryKey: ['audit'] })
  }

  const createMutation = useMutation({
    mutationFn: (input: CreateUserInput) => api.users.create(input),
    onSuccess: (created) => {
      setOpen(false)
      setUsername('')
      setPassword('')
      setRole('operator')
      invalidate()
      pushToast({ title: t('users.created', { username: created.username }), variant: 'success' })
    },
    onError: (error) => {
      pushToast({
        title: t('users.createFailed'),
        description: describeError(error, t),
        variant: 'error',
      })
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ target, input }: { target: User; input: UpdateUserInput }) =>
      api.users.update(target.username, input),
    onSuccess: () => invalidate(),
    onError: (error) => {
      pushToast({
        title: t('users.updateFailed'),
        description: describeError(error, t),
        variant: 'error',
      })
    },
  })

  const roleLabel = (value: UserRole) => t(`users.${value}`)
  const users = usersQuery.data ?? []

  if (!isAdmin) {
    return (
      <>
        <PageHeader title={t('users.title')} description={t('users.subtitle')} />
        <EmptyState icon={ShieldCheck} title={t('users.title')} description={t('users.roleHint')} />
      </>
    )
  }

  return (
    <>
      <PageHeader
        title={t('users.title')}
        description={t('users.subtitle')}
        actions={
          <Button variant="primary" onClick={() => setOpen(true)}>
            <Plus className="h-4 w-4" aria-hidden="true" />
            {t('users.new')}
          </Button>
        }
      />

      <Card>
        <CardHeader
          title={t('users.title')}
          description={t('users.roleHint')}
          actions={<Badge tone="info">{users.length}</Badge>}
        />
        {usersQuery.isLoading ? (
          <CardContent><LoadingState rows={3} /></CardContent>
        ) : usersQuery.isError ? (
          <CardContent><ErrorState error={usersQuery.error} onRetry={() => void usersQuery.refetch()} /></CardContent>
        ) : users.length === 0 ? (
          <CardContent>
            <EmptyState
              icon={UserRound}
              title={t('users.empty')}
              description={t('users.emptyHint')}
              action={<Button variant="primary" onClick={() => setOpen(true)}><Plus className="h-4 w-4" aria-hidden="true" />{t('users.new')}</Button>}
            />
          </CardContent>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-edge-muted text-left text-[11px] uppercase tracking-wide text-slate-500">
                  <th className="px-5 py-3">{t('users.username')}</th>
                  <th className="px-5 py-3">{t('users.role')}</th>
                  <th className="px-5 py-3">{t('users.active')}</th>
                  <th className="px-5 py-3">{t('common.createdAt')}</th>
                  <th className="px-5 py-3">{t('common.actions')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-edge-muted">
                {users.map((item) => (
                  <tr key={item.username}>
                    <td className="px-5 py-3 font-medium text-slate-100">{item.username}</td>
                    <td className="px-5 py-3">
                      <Select
                        value={item.role}
                        onChange={(event) =>
                          updateMutation.mutate({
                            target: item,
                            input: { role: event.target.value as UserRole },
                          })
                        }
                        disabled={updateMutation.isPending}
                      >
                        {(['admin', 'operator', 'viewer'] as const).map((value) => (
                          <option key={value} value={value}>{roleLabel(value)}</option>
                        ))}
                      </Select>
                    </td>
                    <td className="px-5 py-3">
                      <Badge tone={item.active ? 'success' : 'neutral'}>
                        {item.active ? t('users.active') : t('users.inactive')}
                      </Badge>
                    </td>
                    <td className="px-5 py-3 text-slate-400">{formatDate(item.created_at, language)}</td>
                    <td className="px-5 py-3">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() =>
                          updateMutation.mutate({
                            target: item,
                            input: { active: !item.active },
                          })
                        }
                        disabled={updateMutation.isPending}
                      >
                        {item.active ? t('users.deactivate') : t('users.activate')}
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Modal
        open={open}
        onClose={() => { if (!createMutation.isPending) setOpen(false) }}
        title={t('users.new')}
        description={t('users.roleHint')}
        footer={
          <>
            <Button variant="ghost" onClick={() => setOpen(false)} disabled={createMutation.isPending}>{t('common.cancel')}</Button>
            <Button type="submit" form="user-form" variant="primary" loading={createMutation.isPending}>
              {createMutation.isPending ? t('users.creating') : t('users.create')}
            </Button>
          </>
        }
      >
        <form
          id="user-form"
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault()
            createMutation.mutate({ username: username.trim(), password, role })
          }}
        >
          <div>
            <Label htmlFor="user-username">{t('users.username')}</Label>
            <Input id="user-username" value={username} onChange={(event) => setUsername(event.target.value)} required />
          </div>
          <div>
            <Label htmlFor="user-password">{t('users.password')}</Label>
            <Input id="user-password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} minLength={8} required />
          </div>
          <div>
            <Label htmlFor="user-role">{t('users.role')}</Label>
            <Select id="user-role" value={role} onChange={(event) => setRole(event.target.value as UserRole)}>
              {(['admin', 'operator', 'viewer'] as const).map((value) => (
                <option key={value} value={value}>{roleLabel(value)}</option>
              ))}
            </Select>
            <FieldHint>{t('users.roleHint')}</FieldHint>
          </div>
          {createMutation.isError ? <FieldError>{describeError(createMutation.error, t)}</FieldError> : null}
        </form>
      </Modal>
    </>
  )
}
