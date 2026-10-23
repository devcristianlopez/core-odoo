import { useMemo, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { ExternalLink, FolderKanban, Plus, Search, Trash2 } from 'lucide-react'
import { api, type CreateProjectInput } from '../lib/api'
import { queryKeys } from '../lib/query'
import { formatDate } from '../lib/format'
import { safeHttpUrl } from '../lib/services'
import { describeError } from '../lib/errors'
import { useToast } from '../lib/toast-context'
import { PageHeader } from '../components/ui/PageHeader'
import { Card, CardContent, CardFooter } from '../components/ui/Card'
import { Button } from '../components/ui/Button'
import { Input, Label, FieldError, FieldHint } from '../components/ui/Input'
import { Modal } from '../components/ui/Modal'
import { ConfirmDialog } from '../components/ui/ConfirmDialog'
import { EmptyState } from '../components/ui/EmptyState'
import { ErrorState } from '../components/ui/ErrorState'
import { Skeleton } from '../components/ui/Loading'
import { Badge } from '../components/ui/Badge'
import type { Project } from '../lib/types'

const TEMPLATE_SUGGESTIONS = ['odoo', 'odoo-module', 'frontend-starter']
const NAME_PATTERN = /^[a-z0-9](?:[a-z0-9-]{1,38})[a-z0-9]$/

interface FormErrors {
  name?: string
  template?: string
  repoUrl?: string
}

function projectMatches(project: Project, query: string): boolean {
  const needle = query.trim().toLowerCase()
  if (needle === '') return true
  return (
    project.name.toLowerCase().includes(needle) ||
    (project.template ?? '').toLowerCase().includes(needle)
  )
}

function ProjectCardSkeleton() {
  return (
    <Card className="p-5" aria-hidden="true">
      <Skeleton className="h-5 w-1/2" />
      <Skeleton className="mt-3 h-3 w-1/3" />
      <Skeleton className="mt-5 h-3 w-2/3" />
      <Skeleton className="mt-2 h-3 w-1/2" />
    </Card>
  )
}

export default function ProjectsPage() {
  const { t, i18n } = useTranslation()
  const language = i18n.resolvedLanguage ?? i18n.language
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { pushToast } = useToast()

  const [search, setSearch] = useState('')
  const [createOpen, setCreateOpen] = useState(false)
  const [name, setName] = useState('')
  const [template, setTemplate] = useState('odoo')
  const [repoUrl, setRepoUrl] = useState('')
  const [formErrors, setFormErrors] = useState<FormErrors>({})
  const [projectToDelete, setProjectToDelete] = useState<Project | null>(null)

  const projectsQuery = useQuery({
    queryKey: queryKeys.projects,
    queryFn: () => api.projects.list(),
  })

  const invalidateProjects = () => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.projects })
    void queryClient.invalidateQueries({ queryKey: queryKeys.status })
    void queryClient.invalidateQueries({ queryKey: ['audit'] })
  }

  const createMutation = useMutation({
    mutationFn: (input: CreateProjectInput) => api.projects.create(input),
    onSuccess: (project) => {
      setCreateOpen(false)
      setName('')
      setTemplate('odoo')
      setRepoUrl('')
      setFormErrors({})
      invalidateProjects()
      pushToast({ title: t('projects.created', { name: project.name }), variant: 'success' })
      navigate(`/projects/${encodeURIComponent(project.name)}`)
    },
    onError: (error) => {
      pushToast({
        title: t('projects.createFailed'),
        description: describeError(error, t),
        variant: 'error',
      })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (project: Project) => api.projects.remove(project.name),
    onSuccess: (_result, project) => {
      setProjectToDelete(null)
      invalidateProjects()
      pushToast({ title: t('projects.deleted', { name: project.name }), variant: 'success' })
    },
    onError: (error) => {
      pushToast({
        title: t('projects.deleteFailed'),
        description: describeError(error, t),
        variant: 'error',
      })
    },
  })

  const projects = useMemo(() => projectsQuery.data ?? [], [projectsQuery.data])
  const filteredProjects = useMemo(
    () => projects.filter((project) => projectMatches(project, search)),
    [projects, search],
  )

  function resetForm() {
    setCreateOpen(false)
    setFormErrors({})
  }

  function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const errors: FormErrors = {}
    const trimmedName = name.trim()
    if (!NAME_PATTERN.test(trimmedName)) errors.name = t('projects.nameInvalid')
    if (template.trim() === '') errors.template = t('common.required')
    const trimmedRepo = repoUrl.trim()
    if (trimmedRepo !== '' && !safeHttpUrl(trimmedRepo)) errors.repoUrl = t('projects.repoUrlInvalid')
    setFormErrors(errors)
    if (Object.keys(errors).length > 0) return
    createMutation.mutate({
      name: trimmedName,
      template: template.trim(),
      repo_url: trimmedRepo === '' ? undefined : trimmedRepo,
    })
  }

  return (
    <>
      <PageHeader
        title={t('projects.title')}
        description={t('projects.subtitle')}
        actions={
          <Button variant="primary" onClick={() => setCreateOpen(true)}>
            <Plus className="h-4 w-4" aria-hidden="true" />
            {t('projects.newProject')}
          </Button>
        }
      />

      {projectsQuery.isError ? (
        <ErrorState
          error={projectsQuery.error}
          title={t('projects.loadError')}
          onRetry={() => void projectsQuery.refetch()}
        />
      ) : projectsQuery.isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3" role="status">
          <span className="sr-only">{t('common.loading')}</span>
          {Array.from({ length: 6 }).map((_, index) => (
            <ProjectCardSkeleton key={index} />
          ))}
        </div>
      ) : projects.length === 0 ? (
        <EmptyState
          icon={FolderKanban}
          title={t('projects.emptyTitle')}
          description={t('projects.emptyDescription')}
          action={
            <Button variant="primary" onClick={() => setCreateOpen(true)}>
              <Plus className="h-4 w-4" aria-hidden="true" />
              {t('projects.emptyAction')}
            </Button>
          }
        />
      ) : (
        <>
          <div className="mb-4 max-w-sm">
            <label htmlFor="project-search" className="sr-only">
              {t('common.search')}
            </label>
            <div className="relative">
              <Search
                className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500"
                aria-hidden="true"
              />
              <Input
                id="project-search"
                type="search"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder={t('projects.searchPlaceholder')}
                className="pl-9"
              />
            </div>
          </div>

          {filteredProjects.length === 0 ? (
            <EmptyState
              icon={Search}
              title={t('projects.noMatchTitle')}
              description={t('projects.noMatchDescription')}
            />
          ) : (
            <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {filteredProjects.map((project) => {
                const repo = safeHttpUrl(project.repo_url)
                const environmentCount = Array.isArray(project.environments)
                  ? project.environments.length
                  : 0
                return (
                  <li key={project.name}>
                    <Card className="flex h-full flex-col">
                      <CardContent className="flex-1">
                        <div className="flex items-start justify-between gap-2">
                          <Link
                            to={`/projects/${encodeURIComponent(project.name)}`}
                            className="group min-w-0 rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-400"
                          >
                            <h2 className="truncate text-base font-semibold text-white group-hover:text-accent-300">
                              {project.name}
                            </h2>
                          </Link>
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => setProjectToDelete(project)}
                            aria-label={`${t('projects.deleteTitle')}: ${project.name}`}
                            title={t('projects.deleteTitle')}
                            className="text-slate-500 hover:text-danger-400"
                          >
                            <Trash2 className="h-4 w-4" aria-hidden="true" />
                          </Button>
                        </div>
                        <div className="mt-2 flex flex-wrap items-center gap-2">
                          <Badge tone="info">
                            {project.template || t('projects.noTemplate')}
                          </Badge>
                          <Badge tone="neutral">
                            {t('projects.environmentCount', { count: environmentCount })}
                          </Badge>
                        </div>
                        <p className="mt-3 text-xs text-slate-500">
                          {t('projects.createdOn', {
                            date: formatDate(project.created_at, language),
                          })}
                        </p>
                        {repo ? (
                          <a
                            href={repo}
                            target="_blank"
                            rel="noreferrer noopener"
                            aria-label={t('common.openInNewTab')}
                            className="mt-2 inline-flex max-w-full items-center gap-1 truncate rounded text-xs text-slate-400 hover:text-accent-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-400"
                          >
                            <ExternalLink className="h-3 w-3 shrink-0" aria-hidden="true" />
                            <span className="truncate">{project.repo_url}</span>
                          </a>
                        ) : null}
                      </CardContent>
                      <CardFooter className="flex items-center justify-between">
                        <Link
                          to={`/projects/${encodeURIComponent(project.name)}`}
                          className="rounded font-medium text-accent-300 hover:text-accent-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-400"
                        >
                          {t('projects.openProject')}
                        </Link>
                        <span>
                          {t('projects.environmentCount', { count: environmentCount })}
                        </span>
                      </CardFooter>
                    </Card>
                  </li>
                )
              })}
            </ul>
          )}
        </>
      )}

      <Modal
        open={createOpen}
        onClose={() => {
          if (!createMutation.isPending) resetForm()
        }}
        title={t('projects.createTitle')}
        description={t('projects.createDescription')}
        footer={
          <>
            <Button variant="ghost" onClick={resetForm} disabled={createMutation.isPending}>
              {t('common.cancel')}
            </Button>
            <Button
              type="submit"
              form="create-project-form"
              variant="primary"
              loading={createMutation.isPending}
            >
              {createMutation.isPending ? t('projects.creating') : t('projects.createAction')}
            </Button>
          </>
        }
      >
        <form id="create-project-form" onSubmit={handleCreate} noValidate className="space-y-4">
          <div>
            <Label htmlFor="project-name">{t('projects.nameLabel')}</Label>
            <Input
              id="project-name"
              name="name"
              autoFocus
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder={t('projects.namePlaceholder')}
              invalid={Boolean(formErrors.name)}
              aria-describedby={
                formErrors.name ? 'project-name-error' : 'project-name-hint'
              }
            />
            {formErrors.name ? (
              <FieldError id="project-name-error">{formErrors.name}</FieldError>
            ) : (
              <FieldHint id="project-name-hint">{t('projects.nameHint')}</FieldHint>
            )}
          </div>

          <div>
            <Label htmlFor="project-template">{t('projects.templateLabel')}</Label>
            <Input
              id="project-template"
              name="template"
              list="project-template-options"
              value={template}
              onChange={(event) => setTemplate(event.target.value)}
              placeholder={t('projects.templatePlaceholder')}
              invalid={Boolean(formErrors.template)}
              aria-describedby={
                formErrors.template ? 'project-template-error' : 'project-template-hint'
              }
            />
            <datalist id="project-template-options">
              {TEMPLATE_SUGGESTIONS.map((suggestion) => (
                <option key={suggestion} value={suggestion} />
              ))}
            </datalist>
            {formErrors.template ? (
              <FieldError id="project-template-error">{formErrors.template}</FieldError>
            ) : (
              <FieldHint id="project-template-hint">{t('projects.templateHint')}</FieldHint>
            )}
          </div>

          <div>
            <Label htmlFor="project-repo" optional optionalLabel={t('common.optional')}>
              {t('projects.repoUrlLabel')}
            </Label>
            <Input
              id="project-repo"
              name="repo_url"
              type="url"
              inputMode="url"
              value={repoUrl}
              onChange={(event) => setRepoUrl(event.target.value)}
              placeholder={t('projects.repoUrlPlaceholder')}
              invalid={Boolean(formErrors.repoUrl)}
              aria-describedby={formErrors.repoUrl ? 'project-repo-error' : 'project-repo-hint'}
            />
            {formErrors.repoUrl ? (
              <FieldError id="project-repo-error">{formErrors.repoUrl}</FieldError>
            ) : (
              <FieldHint id="project-repo-hint">{t('projects.repoUrlHint')}</FieldHint>
            )}
          </div>
        </form>
      </Modal>

      <ConfirmDialog
        open={projectToDelete !== null}
        onClose={() => {
          if (!deleteMutation.isPending) setProjectToDelete(null)
        }}
        onConfirm={() => {
          if (projectToDelete) deleteMutation.mutate(projectToDelete)
        }}
        title={t('projects.deleteTitle')}
        description={t('projects.deleteDescription', { name: projectToDelete?.name ?? '' })}
        warning={t('projects.deleteWarning')}
        confirmLabel={
          deleteMutation.isPending ? t('common.deleting') : t('projects.deleteAction')
        }
        destructive
        loading={deleteMutation.isPending}
      />
    </>
  )
}
