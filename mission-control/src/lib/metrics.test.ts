import { describe, expect, it } from 'vitest'
import {
  HOST_QUERIES,
  buildEnvironmentQueries,
  extractMetricPoints,
  latestMetricValue,
  mergeHistory,
} from './metrics'

describe('buildEnvironmentQueries', () => {
  it('uses compose project labels and Traefik service names from the contract', () => {
    const queries = buildEnvironmentQueries('smoke-test', 'dev')
    expect(queries.cpu).toContain('container_label_com_docker_compose_project="core-smoke-test-dev"')
    expect(queries.memory).toContain('container_label_com_docker_compose_project="core-smoke-test-dev"')
    expect(queries.p95).toContain('service=~"smoke-test-dev-.*"')
    expect(queries.errorRate).toContain('code=~"5.."')
  })

  it('escapes quotes in names', () => {
    const queries = buildEnvironmentQueries('a"b', 'prod')
    expect(queries.cpu).toContain('core-a\\"b-prod')
  })
})

describe('extractMetricPoints', () => {
  it('parses instant vector values and converts seconds to milliseconds', () => {
    const points = extractMetricPoints({
      status: 'success',
      data: {
        resultType: 'vector',
        result: [{ metric: {}, value: [1_700_000_000, '2.5'] }],
      },
    })
    expect(points).toEqual([{ timestamp: 1_700_000_000_000, value: 2.5 }])
  })

  it('parses matrices, sums multiple series and sorts points', () => {
    const points = extractMetricPoints({
      data: {
        resultType: 'matrix',
        result: [
          {
            metric: { name: 'a' },
            values: [
              [1_700_000_030, '1'],
              [1_700_000_000, '2'],
            ],
          },
          {
            metric: { name: 'b' },
            values: [
              [1_700_000_000, '3'],
              [1_700_000_060, '4'],
            ],
          },
        ],
      },
    })
    expect(points).toEqual([
      { timestamp: 1_700_000_000_000, value: 5 },
      { timestamp: 1_700_000_030_000, value: 1 },
      { timestamp: 1_700_000_060_000, value: 4 },
    ])
  })

  it('drops non-finite samples and malformed payloads', () => {
    expect(
      extractMetricPoints({
        data: { result: [{ value: [1_700_000_000, 'NaN'] }, { value: [1_700_000_000, '+Inf'] }] },
      }),
    ).toEqual([])
    expect(extractMetricPoints(null)).toEqual([])
    expect(extractMetricPoints({ data: { result: 'nope' } })).toEqual([])
  })
})

describe('latestMetricValue', () => {
  it('returns the last sample', () => {
    expect(
      latestMetricValue({
        data: {
          result: [
            { value: [1_700_000_000, '1'] },
            { value: [1_700_000_015, '7'] },
          ],
        },
      }),
    ).toBe(7)
    expect(latestMetricValue({ data: { result: [] } })).toBeNull()
  })
})

describe('mergeHistory', () => {
  it('deduplicates timestamps and keeps ascending order', () => {
    const merged = mergeHistory(
      [
        { timestamp: 1, value: 10 },
        { timestamp: 2, value: 20 },
      ],
      [
        { timestamp: 2, value: 25 },
        { timestamp: 3, value: 30 },
      ],
    )
    expect(merged).toEqual([
      { timestamp: 1, value: 10 },
      { timestamp: 2, value: 25 },
      { timestamp: 3, value: 30 },
    ])
  })

  it('keeps only the newest samples', () => {
    const merged = mergeHistory(
      [],
      [
        { timestamp: 1, value: 1 },
        { timestamp: 2, value: 2 },
        { timestamp: 3, value: 3 },
      ],
      2,
    )
    expect(merged).toEqual([
      { timestamp: 2, value: 2 },
      { timestamp: 3, value: 3 },
    ])
  })

  it('keeps the previous history when no samples arrive', () => {
    const previous = [{ timestamp: 1, value: 1 }]
    expect(mergeHistory(previous, [])).toEqual(previous)
  })
})

describe('HOST_QUERIES', () => {
  it('queries node-exporter metrics', () => {
    expect(HOST_QUERIES.cpu).toContain('node_cpu_seconds_total')
    expect(HOST_QUERIES.memory).toContain('node_memory_MemAvailable_bytes')
    expect(HOST_QUERIES.disk).toContain('node_filesystem_avail_bytes')
  })
})
