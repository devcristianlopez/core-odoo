import type { Environment, Project, ServiceStatus, Stage } from './types'
import { isRunningStatus, isRecord, normalizeStatusKey } from './status'
import { STAGES } from './types'

function serviceNameFromRecord(record: Record<string, unknown>): string | null {
  for (const key of ['name', 'service', 'container', 'container_name', 'id']) {
    const value = record[key]
    if (typeof value === 'string' && value.trim() !== '') return value
  }
  return null
}

function serviceStatusFromUnknown(value: unknown): string | null {
  if (typeof value === 'string') return value
  if (typeof value === 'boolean') return value ? 'running' : 'stopped'
  if (isRecord(value)) {
    for (const key of ['status', 'state', 'health', 'phase']) {
      const candidate = value[key]
      if (typeof candidate === 'string' && candidate.trim() !== '') return candidate
    }
  }
  return null
}

/**
 * `Environment.services` is deliberately loose in the contract: it may be a
 * list of names, a list of objects, or a `{service: status}` map.
 */
export function normalizeServices(input: unknown): ServiceStatus[] {
  const result: ServiceStatus[] = []
  const seen = new Set<string>()

  const push = (name: string, status: string | null) => {
    const key = name.toLowerCase()
    if (seen.has(key)) return
    seen.add(key)
    result.push({ name, status })
  }

  if (Array.isArray(input)) {
    for (const item of input) {
      if (typeof item === 'string') {
        if (item.trim() !== '') push(item, null)
      } else if (isRecord(item)) {
        const name = serviceNameFromRecord(item)
        if (name) push(name, serviceStatusFromUnknown(item))
      }
    }
    return result
  }

  if (isRecord(input)) {
    for (const [name, value] of Object.entries(input)) {
      if (value === null || value === undefined || value === false) continue
      push(name, serviceStatusFromUnknown(value))
    }
  }

  return result
}

export function groupEnvironmentsByStage(
  environments: Environment[],
): Record<Stage, Environment[]> {
  const groups: Record<Stage, Environment[]> = { dev: [], staging: [], prod: [] }
  for (const environment of environments) {
    const stage = environment.stage
    if (stage === 'dev' || stage === 'staging' || stage === 'prod') {
      groups[stage].push(environment)
    }
  }
  return groups
}

export function findEnvironment(
  environments: Environment[],
  stage: string | undefined,
): Environment | null {
  if (!stage) return null
  return environments.find((environment) => environment.stage === stage) ?? null
}

export function countRunningEnvironments(environments: Environment[]): number {
  return environments.reduce(
    (total, environment) => (isRunningStatus(environment.status) ? total + 1 : total),
    0,
  )
}

/** Flattens projects into their environments, skipping malformed payloads. */
export function flattenEnvironments(projects: Project[] | undefined): Environment[] {
  if (!projects) return []
  const environments: Environment[] = []
  for (const project of projects) {
    if (!Array.isArray(project.environments)) continue
    for (const environment of project.environments) {
      environments.push({
        ...environment,
        project: environment.project || project.name,
      })
    }
  }
  return environments
}

const STAGE_SET = new Set<string>(STAGES)

export function isKnownStage(value: unknown): value is Stage {
  return typeof value === 'string' && STAGE_SET.has(value)
}

/** Only http(s) URLs are turned into links (defends against `javascript:`). */
export function safeHttpUrl(value: unknown): string | null {
  if (typeof value !== 'string' || value.trim() === '') return null
  const candidate = value.includes('://') ? value : `http://${value}`
  try {
    const url = new URL(candidate)
    if (url.protocol !== 'http:' && url.protocol !== 'https:') return null
    return url.toString()
  } catch {
    return null
  }
}

export function normalizeStatusLabel(value: unknown): string {
  return normalizeStatusKey(value)
}
