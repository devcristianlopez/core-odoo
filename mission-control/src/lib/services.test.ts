import { describe, expect, it } from 'vitest'
import {
  countRunningEnvironments,
  findEnvironment,
  flattenEnvironments,
  groupEnvironmentsByStage,
  normalizeServices,
  safeHttpUrl,
} from './services'
import type { Environment, Project } from './types'

function environment(project: string, stage: string, status = 'running'): Environment {
  return {
    project,
    stage,
    status,
    url: null,
    compose_project: `core-${project}-${stage}`,
  }
}

describe('normalizeServices', () => {
  it('normalizes lists of names, objects and maps', () => {
    expect(normalizeServices(['odoo', { name: 'postgres', status: 'healthy' }, 'odoo'])).toEqual([
      { name: 'odoo', status: null },
      { name: 'postgres', status: 'healthy' },
    ])
    expect(
      normalizeServices({ odoo: 'running', postgres: { status: 'healthy' }, mailpit: false }),
    ).toEqual([
      { name: 'odoo', status: 'running' },
      { name: 'postgres', status: 'healthy' },
    ])
  })

  it('returns an empty list for malformed input', () => {
    expect(normalizeServices(null)).toEqual([])
    expect(normalizeServices(42)).toEqual([])
  })
})

describe('environment grouping', () => {
  const environments = [
    environment('demo', 'dev'),
    environment('demo', 'prod', 'stopped'),
    environment('demo', 'staging'),
    environment('other', 'dev'),
  ]

  it('groups by known stages', () => {
    const grouped = groupEnvironmentsByStage(environments)
    expect(grouped.dev).toHaveLength(2)
    expect(grouped.staging).toHaveLength(1)
    expect(grouped.prod).toHaveLength(1)
  })

  it('finds an environment by stage', () => {
    expect(findEnvironment(environments, 'staging')?.project).toBe('demo')
    expect(findEnvironment(environments, 'unknown')).toBeNull()
  })

  it('counts running environments', () => {
    expect(countRunningEnvironments(environments)).toBe(3)
  })
})

describe('flattenEnvironments', () => {
  it('fills missing project names and ignores malformed projects', () => {
    const projects: Project[] = [
      {
        name: 'demo',
        template: 'odoo',
        environments: [
          { project: '', stage: 'dev', status: 'running', url: null, compose_project: 'x' },
        ],
      },
      { name: 'empty', template: 'odoo' },
    ]
    const flattened = flattenEnvironments(projects)
    expect(flattened).toHaveLength(1)
    expect(flattened[0]?.project).toBe('demo')
    expect(flattenEnvironments(undefined)).toEqual([])
  })
})

describe('safeHttpUrl', () => {
  it('accepts http(s) URLs and hostnames', () => {
    expect(safeHttpUrl('https://example.com/app')).toBe('https://example.com/app')
    expect(safeHttpUrl('core-odoo.10.0.0.2.nip.io')).toBe('http://core-odoo.10.0.0.2.nip.io/')
  })

  it('rejects unsafe protocols and invalid values', () => {
    expect(safeHttpUrl('javascript:alert(1)')).toBeNull()
    expect(safeHttpUrl('')).toBeNull()
    expect(safeHttpUrl(null)).toBeNull()
  })
})
