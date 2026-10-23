import { useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Database, GitCompare, History, Plus, RotateCcw, Rocket } from 'lucide-react'
import { api, type CreateIterationInput } from '../../lib/api'
import { queryKeys } from '../../lib/query'
import { isStage, type Iteration, type IterationDiff } from '../../lib/types'
import { formatDate } from '../../lib/format'
import { describeError } from '../../lib/errors'
import { useToast } from '../../lib/toast-context'
import { Card, CardContent, CardHeader } from '../ui/Card'
import { Button } from '../ui/Button'
import { Badge } from '../ui/Badge'
import { Input, Label, FieldHint, FieldError } from '../ui/Input'
import { Modal } from '../ui/Modal'
import { EmptyState } from '../ui/EmptyState'
import { ErrorState } from '../ui/ErrorState'
import { LoadingState } from '../ui/Loading'

export function IterationsPanel({
  project,
  onChanged,
  canWrite = true,
}: {
  project: string
  onChanged: () => void
  canWrite?: boolean
}): JSX.Element {
  const { t, i18n } = useTranslation()
  const language = i18n.resolvedLanguage ?? i18n.language
  const queryClient = useQueryClient()
  const { pushToast } = useToast()
  const [createOpen, setCreateOpen] = useState(false)
  const [version, setVersion] = useState('')
  const [title, setTitle] = useState('')
  const [notes, setNotes] = useState('')
  const [diff, setDiff] = useState<IterationDiff | null>(null)
  const [diffOpen, setDiffOpen] = useState(false)

  const iterationsQuery = useQuery({
    queryKey: queryKeys.iterations(project),
    queryFn: () => api.iterations.list(project),
  })

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.iterations(project) })
    onChanged()
  }

  const createMutation = useMutation({
    mutationFn: (input: CreateIterationInput) => api.iterations.create(project, input),
    onSuccess: (iteration) => {
      setCreateOpen(false)
      setVersion('')
      setTitle('')
      setNotes('')
      refresh()
      pushToast({
        title: t('iterations.created', { version: iteration.version }),
        variant: 'success',
      })
    },
    onError: (error) => {
      pushToast({
        title: t('iterations.createFailed'),
        description: describeError(error, t),
        variant: 'error',
      })
    },
  })

  const restoreMutation = useMutation({
    mutationFn: (iteration: Iteration) => api.iterations.restore(project, iteration.version),
    onSuccess: (iteration) => {
      refresh()
      pushToast({
        title: t('iterations.restored', { version: iteration.version }),
        variant: 'success',
      })
    },
    onError: (error) => {
      pushToast({
        title: t('iterations.restoreFailed'),
        description: describeError(error, t),
        variant: 'error',
      })
    },
  })

  const deployMutation = useMutation({
    mutationFn: async (iteration: Iteration) => {
      await api.iterations.restore(project, iteration.version)
      const stage = isStage(iteration.stage) ? iteration.stage : 'dev'
      const confirm =
        stage === 'prod'
          ? window.prompt(t('iterations.prodConfirmPrompt', { project })) ?? ''
          : undefined
      if (stage === 'prod' && confirm !== project) {
        throw new Error(t('iterations.prodConfirmMismatch'))
      }
      return api.environments.deploy(project, { stage, iteration: iteration.version, confirm })
    },
    onSuccess: (_environment, iteration) => {
      refresh()
      const stage = isStage(iteration.stage) ? iteration.stage : 'dev'
      pushToast({
        title: t('iterations.deployed', { version: iteration.version, stage }),
        variant: 'success',
      })
    },
    onError: (error) => {
      pushToast({
        title: t('iterations.deployFailed'),
        description: describeError(error, t),
        variant: 'error',
      })
    },
  })

  const diffMutation = useMutation({
    mutationFn: (iteration: Iteration) => api.iterations.diff(project, iteration.version),
    onSuccess: (payload) => {
      setDiff(payload)
      setDiffOpen(true)
    },
    onError: (error) => {
      pushToast({
        title: t('iterations.diffFailed'),
        description: describeError(error, t),
        variant: 'error',
      })
    },
  })

  const backupMutation = useMutation({
    mutationFn: (iteration: Iteration) =>
      api.iterations.backup(
        project,
        iteration.version,
        isStage(iteration.stage) ? iteration.stage : 'dev',
      ),
    onSuccess: (_result, iteration) => {
      pushToast({
        title: t('iterations.backupCreated', { version: iteration.version }),
        variant: 'success',
      })
    },
    onError: (error) => {
      pushToast({
        title: t('iterations.backupFailed'),
        description: describeError(error, t),
        variant: 'error',
      })
    },
  })

  const iterations = iterationsQuery.data ?? []

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    createMutation.mutate({
      version: version.trim(),
      title: title.trim(),
      notes: notes.trim(),
    })
  }

  const restore = (iteration: Iteration) => {
    if (!window.confirm(t('iterations.restoreConfirm', { version: iteration.version }))) return
    restoreMutation.mutate(iteration)
  }

  const deploy = (iteration: Iteration) => {
    const stage = isStage(iteration.stage) ? iteration.stage : 'dev'
    if (!window.confirm(t('iterations.deployConfirm', { version: iteration.version, stage }))) return
    deployMutation.mutate(iteration)
  }

  return (
    <>
      <Card>
        <CardHeader
          title={t('iterations.title')}
          description={t('iterations.subtitle')}
          actions={
            canWrite ? (
              <Button variant="primary" size="sm" onClick={() => setCreateOpen(true)}>
                <Plus className="h-3.5 w-3.5" aria-hidden="true" />
                {t('iterations.new')}
              </Button>
            ) : undefined
          }
        />
        {iterationsQuery.isLoading ? (
          <CardContent>
            <LoadingState rows={3} />
          </CardContent>
        ) : iterationsQuery.isError ? (
          <CardContent>
            <ErrorState
              error={iterationsQuery.error}
              onRetry={() => void iterationsQuery.refetch()}
            />
          </CardContent>
        ) : iterations.length === 0 ? (
          <CardContent>
            <EmptyState
              icon={History}
              title={t('iterations.empty')}
              description={t('iterations.emptyHint')}
              action={
                canWrite ? (
                  <Button variant="primary" size="sm" onClick={() => setCreateOpen(true)}>
                    <Plus className="h-3.5 w-3.5" aria-hidden="true" />
                    {t('iterations.new')}
                  </Button>
                ) : undefined
              }
            />
          </CardContent>
        ) : (
          <ul className="divide-y divide-edge-muted">
            {iterations.map((iteration) => (
              <li key={iteration.version} className="flex flex-col gap-3 px-5 py-4 sm:flex-row sm:items-start sm:justify-between">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone="info">v{iteration.version}</Badge>
                    <span className="text-sm font-medium text-slate-100">{iteration.title}</span>
                    <Badge tone={iteration.status === 'deployed' ? 'success' : iteration.status === 'failed' ? 'danger' : 'neutral'}>
                      {iteration.status}
                    </Badge>
                    {iteration.stage ? <Badge tone="neutral">{iteration.stage}</Badge> : null}
                  </div>
                  {iteration.notes ? <p className="mt-1 text-xs text-slate-400">{iteration.notes}</p> : null}
                  <p className="mt-1 text-[11px] text-slate-500">
                    {t('iterations.createdOn', { date: formatDate(iteration.created_at, language) })}
                    {iteration.has_snapshot ? ` · ${t('iterations.snapshot')}` : ` · ${t('iterations.noSnapshot')}`}
                  </p>
                </div>
                <div className="flex shrink-0 flex-wrap gap-1.5">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => diffMutation.mutate(iteration)}
                    disabled={diffMutation.isPending}
                  >
                    <GitCompare className="h-3.5 w-3.5" aria-hidden="true" />
                    {t('iterations.diff')}
                  </Button>
                  {canWrite ? (
                    <>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => restore(iteration)}
                        disabled={!iteration.has_snapshot || restoreMutation.isPending || deployMutation.isPending}
                      >
                        <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
                        {restoreMutation.isPending ? t('iterations.restoring') : t('iterations.restore')}
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => backupMutation.mutate(iteration)}
                        disabled={!iteration.has_snapshot || backupMutation.isPending}
                      >
                        <Database className="h-3.5 w-3.5" aria-hidden="true" />
                        {t('iterations.backup')}
                      </Button>
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => deploy(iteration)}
                        disabled={!iteration.has_snapshot || deployMutation.isPending}
                      >
                        <Rocket className="h-3.5 w-3.5" aria-hidden="true" />
                        {deployMutation.isPending ? t('iterations.deploying') : t('iterations.deploy')}
                      </Button>
                    </>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Modal
        open={createOpen}
        onClose={() => {
          if (!createMutation.isPending) setCreateOpen(false)
        }}
        title={t('iterations.new')}
        description={t('iterations.subtitle')}
        footer={
          <>
            <Button variant="ghost" onClick={() => setCreateOpen(false)} disabled={createMutation.isPending}>
              {t('common.cancel')}
            </Button>
            <Button type="submit" form="iteration-form" variant="primary" loading={createMutation.isPending}>
              {createMutation.isPending ? t('iterations.creating') : t('iterations.create')}
            </Button>
          </>
        }
      >
        <form id="iteration-form" className="space-y-4" onSubmit={submit}>
          <div>
            <Label htmlFor="iteration-version">{t('iterations.version')}</Label>
            <Input id="iteration-version" value={version} onChange={(event) => setVersion(event.target.value)} placeholder="0.1.0" required />
          </div>
          <div>
            <Label htmlFor="iteration-title">{t('iterations.titleLabel')}</Label>
            <Input id="iteration-title" value={title} onChange={(event) => setTitle(event.target.value)} placeholder="First release" required />
          </div>
          <div>
            <Label htmlFor="iteration-notes" optional optionalLabel={t('common.optional')}>{t('iterations.notes')}</Label>
            <textarea
              id="iteration-notes"
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
              rows={3}
              className="w-full rounded-lg border border-edge bg-surface-muted px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:border-accent-500 focus:outline-none focus:ring-2 focus:ring-accent-500/30"
            />
            <FieldHint>{t('iterations.notesHint')}</FieldHint>
          </div>
          {createMutation.isError ? <FieldError>{describeError(createMutation.error, t)}</FieldError> : null}
        </form>
      </Modal>

      <Modal
        open={diffOpen}
        onClose={() => setDiffOpen(false)}
        title={t('iterations.diffTitle')}
        description={diff ? `${diff.from_version ?? '∅'} → ${diff.to_version}` : undefined}
        size="lg"
        footer={
          <Button variant="ghost" onClick={() => setDiffOpen(false)}>
            {t('common.close')}
          </Button>
        }
      >
        {diff ? (
          <div className="space-y-4">
            {diff.added.length === 0 && diff.modified.length === 0 && diff.deleted.length === 0 ? (
              <p className="text-sm text-slate-400">{t('iterations.noChanges')}</p>
            ) : null}
            {(['added', 'modified', 'deleted'] as const).map((key) =>
              diff[key].length > 0 ? (
                <div key={key}>
                  <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">
                    {t(`iterations.${key}`)} · {diff[key].length}
                  </p>
                  <ul className="max-h-48 overflow-auto rounded-lg border border-edge-muted bg-surface-muted p-3 font-mono text-xs text-slate-300">
                    {diff[key].map((file) => (
                      <li key={file}>{file}</li>
                    ))}
                  </ul>
                </div>
              ) : null,
            )}
          </div>
        ) : (
          <LoadingState rows={3} />
        )}
      </Modal>
    </>
  )
}
