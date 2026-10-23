import { useMemo, useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import {
  ChevronRight,
  ExternalLink,
  Play,
  Plus,
  RotateCw,
  Square,
  Trash2,
} from 'lucide-react'
import { api, ApiError, type DeployInput } from '../lib/api'
import { queryKeys } from '../lib/query'
import { STAGES, type Environment, type Stage } from '../lib/types'
import { groupEnvironmentsByStage, safeHttpUrl } from '../lib/services'
import { isRunningStatus } from '../lib/status'
import { formatDate, formatRelativeTime } from '../lib/format'
import { describeError } from '../lib/errors'
import { useToast } from '../lib/toast-context'
import { useAuth } from '../lib/auth-context'
import { PageHeader } from '../components/ui/PageHeader'
import { Card, CardContent, CardFooter } from '../components/ui/Card'
import { Button } from '../components/ui/Button'
import { Badge } from '../components/ui/Badge'
import { Input, Label, Select, FieldHint, FieldError } from '../components/ui/Input'
import { Modal } from '../components/ui/Modal'
import { ConfirmDialog } from '../components/ui/ConfirmDialog'
import { EmptyState } from '../components/ui/EmptyState'
import { ErrorState } from '../components/ui/ErrorState'
import { LoadingState } from '../components/ui/Loading'
import { StatusBadge } from '../components/StatusBadge'
import { ServiceBadges } from '../components/environments/ServiceBadges'
import { IterationsPanel } from '../components/iterations/IterationsPanel'

type EnvironmentAction = 'start' | 'stop' | 'restart'

export default function ProjectDetailPage() {
  const { t, i18n } = useTranslation()
  const language = i18n.resolvedLanguage ?? i18n.language
  const params = useParams<{ name: string }>()
  const name = params.name ?? ''
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { pushToast } = useToast()
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin'
  const canWrite = user?.role === 'admin' || user?.role === 'operator'

  const [deployOpen, setDeployOpen] = useState(false)
  const [deployStage, setDeployStage] = useState<Stage>('dev')
  const [branch, setBranch] = useState('')
  const [modules, setModules] = useState('')
  const [deleteProjectOpen, setDeleteProjectOpen] = useState(false)
  const [environmentToDelete, setEnvironmentToDelete] = useState<Environment | null>(null)

  const projectQuery = useQuery({
    queryKey: queryKeys.project(name),
    queryFn: () => api.projects.get(name),
    enabled: name !== '',
    refetchInterval: 30_000,
  })
  const environmentsQuery = useQuery({
    queryKey: queryKeys.environments(name),
    queryFn: () => api.environments.list(name),
    enabled: name !== '',
    refetchInterval: 15_000,
  })

  const project = projectQuery.data
  const environments = useMemo(
    () => environmentsQuery.data ?? project?.environments ?? [],
    [environmentsQuery.data, project?.environments],
  )
  const grouped = useMemo(() => groupEnvironmentsByStage(environments), [environments])

  const invalidateAll = () => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.project(name) })
    void queryClient.invalidateQueries({ queryKey: queryKeys.environments(name) })
    void queryClient.invalidateQueries({ queryKey: queryKeys.status })
    void queryClient.invalidateQueries({ queryKey: ['audit'] })
  }

  const stageLabel = (stage: string) => t(`stages.${stage}`, { defaultValue: stage })

  const deployMutation = useMutation({
    mutationFn: (input: DeployInput) => api.environments.deploy(name, input),
    onSuccess: (environment, input) => {
      setDeployOpen(false)
      setBranch('')
      setModules('')
      invalidateAll()
      pushToast({
        title: t('project.deployed', {
          project: name,
          stage: stageLabel(input.stage),
        }),
        variant: 'success',
      })
      navigate(
        `/projects/${encodeURIComponent(name)}/environments/${encodeURIComponent(environment.stage || input.stage)}`,
      )
    },
    onError: (error) => {
      pushToast({
        title: t('project.deployFailed'),
        description: describeError(error, t),
        variant: 'error',
      })
    },
  })

  const environmentActionMutation = useMutation({
    mutationFn: ({ action, stage }: { action: EnvironmentAction; stage: string }) => {
      if (action === 'start') return api.environments.start(name, stage)
      if (action === 'stop') return api.environments.stop(name, stage)
      return api.environments.restart(name, stage)
    },
    onSuccess: (_environment, variables) => {
      invalidateAll()
      const toastKey =
        variables.action === 'start'
          ? 'project.startToast'
          : variables.action === 'stop'
            ? 'project.stopToast'
            : 'project.restartToast'
      pushToast({
        title: t(toastKey, { project: name, stage: stageLabel(variables.stage) }),
        variant: 'success',
      })
    },
    onError: (error) => {
      pushToast({
        title: t('project.envActionFailed'),
        description: describeError(error, t),
        variant: 'error',
      })
    },
  })

  const deleteEnvironmentMutation = useMutation({
    mutationFn: (environment: Environment) =>
      api.environments.remove(name, environment.stage),
    onSuccess: (_result, environment) => {
      setEnvironmentToDelete(null)
      invalidateAll()
      pushToast({
        title: t('project.environmentDeleted', {
          project: name,
          stage: stageLabel(environment.stage),
        }),
        variant: 'success',
      })
    },
    onError: (error) => {
      pushToast({
        title: t('project.environmentDeleteFailed'),
        description: describeError(error, t),
        variant: 'error',
      })
    },
  })

  const deleteProjectMutation = useMutation({
    mutationFn: () => api.projects.remove(name),
    onSuccess: () => {
      setDeleteProjectOpen(false)
      invalidateAll()
      pushToast({ title: t('project.projectDeleted', { name }), variant: 'success' })
      navigate('/projects')
    },
    onError: (error) => {
      pushToast({
        title: t('project.deleteProjectFailed'),
        description: describeError(error, t),
        variant: 'error',
      })
    },
  })

  function openDeploy(stage: Stage) {
    setDeployStage(stage)
    setDeployOpen(true)
  }

  function handleDeploy(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const input: DeployInput = { stage: deployStage }
    if (branch.trim() !== '') input.branch = branch.trim()
    const moduleList = modules
      .split(',')
      .map((module) => module.trim())
      .filter((module) => module !== '')
    if (moduleList.length > 0) input.modules = moduleList
    deployMutation.mutate(input)
  }

  const actionPendingFor = (stage: string) =>
    environmentActionMutation.isPending && environmentActionMutation.variables?.stage === stage

  if (projectQuery.isLoading && !project) {
    return (
      <>
        <PageHeader title={name || t('common.loading')} back={{ to: '/projects', label: t('project.backToProjects') }} />
        <LoadingState rows={4} />
      </>
    )
  }

  if (projectQuery.isError && !project) {
    const notFound = projectQuery.error instanceof ApiError && projectQuery.error.status === 404
    if (notFound) {
      return (
        <>
          <PageHeader
            title={t('project.notFoundTitle')}
            back={{ to: '/projects', label: t('project.backToProjects') }}
          />
          <EmptyState
            title={t('project.notFoundTitle')}
            description={t('project.notFoundDescription')}
            action={
              <Link
                to="/projects"
                className="inline-flex h-9 items-center rounded-lg border border-edge bg-surface-raised px-3 text-xs font-medium text-slate-200 hover:bg-surface-overlay focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-400"
              >
                {t('project.backToProjects')}
              </Link>
            }
          />
        </>
      )
    }
    return (
      <>
        <PageHeader
          title={name}
          back={{ to: '/projects', label: t('project.backToProjects') }}
        />
        <ErrorState
          error={projectQuery.error}
          title={t('project.loadError')}
          onRetry={() => void projectQuery.refetch()}
        />
      </>
    )
  }

  const repository = safeHttpUrl(project?.repo_url)

  return (
    <>
      <PageHeader
        back={{ to: '/projects', label: t('project.backToProjects') }}
        title={project?.name ?? name}
        description={
          project
            ? t('projects.createdOn', { date: formatDate(project.created_at, language) })
            : undefined
        }
        actions={
          <>
            <Button
              variant="secondary"
              size="icon"
              onClick={() => {
                void projectQuery.refetch()
                void environmentsQuery.refetch()
              }}
              aria-label={t('common.refresh')}
              title={t('common.refresh')}
            >
              <RotateCw
                className={
                  projectQuery.isFetching || environmentsQuery.isFetching
                    ? 'h-4 w-4 animate-spin'
                    : 'h-4 w-4'
                }
                aria-hidden="true"
              />
            </Button>
            {isAdmin ? (
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setDeleteProjectOpen(true)}
                aria-label={t('project.deleteProject')}
                title={t('project.deleteProject')}
                className="text-slate-500 hover:text-danger-400"
              >
                <Trash2 className="h-4 w-4" aria-hidden="true" />
              </Button>
            ) : null}
            {canWrite ? (
              <Button variant="primary" onClick={() => openDeploy('dev')}>
                <Plus className="h-4 w-4" aria-hidden="true" />
                {t('project.deployAction')}
              </Button>
            ) : null}
          </>
        }
      />

      <Card className="mb-6">
        <CardContent>
          <dl className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <dt className="text-[11px] uppercase tracking-wide text-slate-500">
                {t('common.template')}
              </dt>
              <dd className="mt-1">
                <Badge tone="info">{project?.template || t('projects.noTemplate')}</Badge>
              </dd>
            </div>
            <div className="min-w-0">
              <dt className="text-[11px] uppercase tracking-wide text-slate-500">
                {t('project.repository')}
              </dt>
              <dd className="mt-1 truncate text-sm text-slate-300">
                {repository ? (
                  <a
                    href={repository}
                    target="_blank"
                    rel="noreferrer noopener"
                    className="inline-flex max-w-full items-center gap-1 rounded text-accent-300 hover:text-accent-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-400"
                  >
                    <ExternalLink className="h-3 w-3 shrink-0" aria-hidden="true" />
                    <span className="truncate">{project?.repo_url}</span>
                  </a>
                ) : (
                  <span className="text-slate-500">{t('common.notAvailable')}</span>
                )}
              </dd>
            </div>
            <div>
              <dt className="text-[11px] uppercase tracking-wide text-slate-500">
                {t('common.createdAt')}
              </dt>
              <dd className="mt-1 text-sm text-slate-300">
                {formatDate(project?.created_at, language)}
              </dd>
            </div>
            <div>
              <dt className="text-[11px] uppercase tracking-wide text-slate-500">
                {t('project.environmentsTitle')}
              </dt>
              <dd className="mt-1 text-sm text-slate-300">
                {t('projects.environmentCount', { count: environments.length })}
              </dd>
            </div>
          </dl>
        </CardContent>
      </Card>

      {environmentsQuery.isError ? (
        <ErrorState
          error={environmentsQuery.error}
          title={t('project.loadError')}
          onRetry={() => void environmentsQuery.refetch()}
          className="mb-6"
        />
      ) : null}

      <div className="grid gap-5 lg:grid-cols-3">
        {STAGES.map((stage) => {
          const stageEnvironments = grouped[stage]
          return (
            <section key={stage} aria-labelledby={`stage-${stage}`} className="flex flex-col">
              <div className="mb-3 flex items-center justify-between gap-2">
                <h2 id={`stage-${stage}`} className="text-sm font-semibold text-white">
                  {stageLabel(stage)}
                </h2>
                <Badge tone={stageEnvironments.length > 0 ? 'info' : 'neutral'}>
                  {t('projects.environmentCount', { count: stageEnvironments.length })}
                </Badge>
              </div>

              {stageEnvironments.length === 0 ? (
                <Card className="flex flex-1 flex-col items-center justify-center gap-2 border-dashed px-5 py-8 text-center">
                  <p className="text-sm font-medium text-slate-300">
                    {t('project.emptyStage', { stage: stageLabel(stage) })}
                  </p>
                  <p className="text-xs text-slate-500">{t('project.emptyStageHint')}</p>
                  {canWrite ? (
                    <Button size="sm" className="mt-2" onClick={() => openDeploy(stage)}>
                      <Plus className="h-3.5 w-3.5" aria-hidden="true" />
                      {t('project.deployStage', { stage: stageLabel(stage) })}
                    </Button>
                  ) : null}
                </Card>
              ) : (
                <div className="flex flex-1 flex-col gap-4">
                  {stageEnvironments.map((environment) => {
                    const running = isRunningStatus(environment.status)
                    const url = safeHttpUrl(environment.url)
                    const pending = actionPendingFor(environment.stage)
                    return (
                      <Card key={`${environment.project}-${environment.stage}`} className="flex flex-col">
                        <CardContent className="flex-1">
                          <div className="flex items-start justify-between gap-2">
                            <StatusBadge status={environment.status} />
                            <div className="flex flex-wrap items-center justify-end gap-0.5">
                              {canWrite ? (
                                <>
                              <Button
                                variant="ghost"
                                size="icon"
                                className="h-8 w-8"
                                onClick={() =>
                                  environmentActionMutation.mutate({
                                    action: 'start',
                                    stage: environment.stage,
                                  })
                                }
                                disabled={running || pending}
                                aria-label={`${t('common.start')}: ${environment.project} ${stageLabel(environment.stage)}`}
                                title={t('common.start')}
                              >
                                <Play className="h-3.5 w-3.5" aria-hidden="true" />
                              </Button>
                              <Button
                                variant="ghost"
                                size="icon"
                                className="h-8 w-8"
                                onClick={() =>
                                  environmentActionMutation.mutate({
                                    action: 'stop',
                                    stage: environment.stage,
                                  })
                                }
                                disabled={!running || pending}
                                aria-label={`${t('common.stop')}: ${environment.project} ${stageLabel(environment.stage)}`}
                                title={t('common.stop')}
                              >
                                <Square className="h-3.5 w-3.5" aria-hidden="true" />
                              </Button>
                              <Button
                                variant="ghost"
                                size="icon"
                                className="h-8 w-8"
                                onClick={() =>
                                  environmentActionMutation.mutate({
                                    action: 'restart',
                                    stage: environment.stage,
                                  })
                                }
                                disabled={pending}
                                aria-label={`${t('common.restart')}: ${environment.project} ${stageLabel(environment.stage)}`}
                                title={t('common.restart')}
                              >
                                <RotateCw className="h-3.5 w-3.5" aria-hidden="true" />
                              </Button>
                              </>
                              ) : null}
                              {isAdmin ? (
                              <Button
                                variant="ghost"
                                size="icon"
                                className="h-8 w-8 text-slate-500 hover:text-danger-400"
                                onClick={() => setEnvironmentToDelete(environment)}
                                aria-label={`${t('environment.deleteEnvironment')}: ${environment.project} ${stageLabel(environment.stage)}`}
                                title={t('environment.deleteEnvironment')}
                              >
                                <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                              </Button>
                              ) : null}
                            </div>
                          </div>

                          <div className="mt-3">
                            {url ? (
                              <a
                                href={url}
                                target="_blank"
                                rel="noreferrer noopener"
                                className="inline-flex max-w-full items-center gap-1 rounded text-xs text-accent-300 hover:text-accent-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-400"
                              >
                                <ExternalLink className="h-3 w-3 shrink-0" aria-hidden="true" />
                                <span className="truncate">{environment.url}</span>
                              </a>
                            ) : (
                              <p className="text-xs text-slate-500">{t('environment.noUrl')}</p>
                            )}
                          </div>

                          <dl className="mt-3 space-y-1 text-xs">
                            <div className="flex items-center justify-between gap-2">
                              <dt className="text-slate-500">{t('environment.composeProject')}</dt>
                              <dd
                                className="truncate font-mono text-[11px] text-slate-400"
                                title={environment.compose_project}
                              >
                                {environment.compose_project || t('common.notAvailable')}
                              </dd>
                            </div>
                            <div className="flex items-center justify-between gap-2">
                              <dt className="text-slate-500">{t('project.branchLabel')}</dt>
                              <dd className="truncate font-mono text-[11px] text-slate-400" title={environment.branch ?? 'main'}>
                                {environment.branch || 'main'}
                              </dd>
                            </div>
                            <div className="flex items-center justify-between gap-2">
                              <dt className="text-slate-500">{t('common.updatedAt')}</dt>
                              <dd className="text-slate-400">
                                {formatRelativeTime(
                                  environment.updated_at ?? environment.created_at,
                                  language,
                                )}
                              </dd>
                            </div>
                          </dl>

                          <div className="mt-3">
                            <p className="mb-1.5 text-[11px] uppercase tracking-wide text-slate-500">
                              {t('common.services')}
                            </p>
                            <ServiceBadges
                              services={environment.services}
                              emptyLabel={t('project.noServices')}
                            />
                          </div>
                        </CardContent>
                        <CardFooter>
                          <Link
                            to={`/projects/${encodeURIComponent(environment.project || name)}/environments/${encodeURIComponent(environment.stage)}`}
                            className="inline-flex items-center gap-1 rounded font-medium text-accent-300 hover:text-accent-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-400"
                          >
                            {t('project.openEnvironment')}
                            <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
                          </Link>
                        </CardFooter>
                      </Card>
                    )
                  })}
                </div>
              )}
            </section>
          )
        })}
      </div>

      <div className="mt-6">
        <IterationsPanel project={name} onChanged={invalidateAll} canWrite={canWrite} />
      </div>

      <Modal
        open={deployOpen}
        onClose={() => {
          if (!deployMutation.isPending) setDeployOpen(false)
        }}
        title={t('project.deployTitle')}
        description={t('project.deployDescription', { project: name })}
        footer={
          <>
            <Button
              variant="ghost"
              onClick={() => setDeployOpen(false)}
              disabled={deployMutation.isPending}
            >
              {t('common.cancel')}
            </Button>
            <Button
              type="submit"
              form="deploy-environment-form"
              variant="primary"
              loading={deployMutation.isPending}
            >
              {deployMutation.isPending ? t('project.deploying') : t('project.deploySubmit')}
            </Button>
          </>
        }
      >
        <form id="deploy-environment-form" onSubmit={handleDeploy} noValidate className="space-y-4">
          <div>
            <Label htmlFor="deploy-stage">{t('common.stage')}</Label>
            <Select
              id="deploy-stage"
              value={deployStage}
              onChange={(event) => {
                const value = event.target.value
                if (value === 'dev' || value === 'staging' || value === 'prod') {
                  setDeployStage(value)
                }
              }}
              aria-describedby="deploy-stage-hint"
            >
              {STAGES.map((stage) => (
                <option key={stage} value={stage}>
                  {stageLabel(stage)}
                </option>
              ))}
            </Select>
            <FieldHint id="deploy-stage-hint">{t('project.stageHint')}</FieldHint>
          </div>
          <div>
            <Label htmlFor="deploy-branch" optional optionalLabel={t('common.optional')}>
              {t('project.branchLabel')}
            </Label>
            <Input
              id="deploy-branch"
              value={branch}
              onChange={(event) => setBranch(event.target.value)}
              placeholder={t('project.branchPlaceholder')}
              aria-describedby="deploy-branch-hint"
            />
            <FieldHint id="deploy-branch-hint">{t('project.branchHint')}</FieldHint>
          </div>
          <div>
            <Label htmlFor="deploy-modules" optional optionalLabel={t('common.optional')}>
              {t('project.modulesLabel')}
            </Label>
            <Input
              id="deploy-modules"
              value={modules}
              onChange={(event) => setModules(event.target.value)}
              placeholder={t('project.modulesPlaceholder')}
              aria-describedby="deploy-modules-hint"
            />
            <FieldHint id="deploy-modules-hint">{t('project.modulesHint')}</FieldHint>
          </div>
          {deployMutation.isError ? (
            <FieldError>{describeError(deployMutation.error, t)}</FieldError>
          ) : null}
        </form>
      </Modal>

      <ConfirmDialog
        open={deleteProjectOpen}
        onClose={() => {
          if (!deleteProjectMutation.isPending) setDeleteProjectOpen(false)
        }}
        onConfirm={() => deleteProjectMutation.mutate()}
        title={t('project.deleteTitle')}
        description={t('project.deleteDescription', { name })}
        warning={t('project.deleteWarning')}
        confirmLabel={
          deleteProjectMutation.isPending ? t('common.deleting') : t('project.deleteProject')
        }
        destructive
        loading={deleteProjectMutation.isPending}
      />

      <ConfirmDialog
        open={environmentToDelete !== null}
        onClose={() => {
          if (!deleteEnvironmentMutation.isPending) setEnvironmentToDelete(null)
        }}
        onConfirm={() => {
          if (environmentToDelete) deleteEnvironmentMutation.mutate(environmentToDelete)
        }}
        title={t('project.deleteEnvironmentTitle')}
        description={t('project.deleteEnvironmentDescription', {
          project: name,
          stage: environmentToDelete ? stageLabel(environmentToDelete.stage) : '',
        })}
        warning={t('project.deleteEnvironmentWarning')}
        confirmLabel={
          deleteEnvironmentMutation.isPending
            ? t('common.deleting')
            : t('environment.deleteEnvironment')
        }
        destructive
        loading={deleteEnvironmentMutation.isPending}
      />
    </>
  )
}
