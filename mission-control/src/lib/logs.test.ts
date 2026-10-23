import { describe, expect, it } from 'vitest'
import { filterLogLines, logsToText, splitLogLines, stripAnsi, tailLines } from './logs'

describe('stripAnsi', () => {
  it('removes color and control sequences', () => {
    expect(stripAnsi('\u001b[31merror\u001b[0m')).toBe('error')
    expect(stripAnsi('\u001b]0;title\u0007text')).toBe('text')
  })
})

describe('splitLogLines', () => {
  it('splits, strips ANSI and normalizes CRLF', () => {
    expect(splitLogLines('\u001b[32mone\u001b[0m\r\ntwo\n')).toEqual(['one', 'two'])
    expect(splitLogLines(null)).toEqual([])
  })
})

describe('filterLogLines', () => {
  const lines = ['INFO server started', 'ERROR database down', 'INFO ready']

  it('filters case-insensitively', () => {
    expect(filterLogLines(lines, 'error')).toEqual(['ERROR database down'])
    expect(filterLogLines(lines, '  ')).toEqual(lines)
    expect(filterLogLines(lines, 'missing')).toEqual([])
  })
})

describe('tailLines', () => {
  it('keeps the last N lines', () => {
    expect(tailLines(['a', 'b', 'c'], 2)).toEqual(['b', 'c'])
    expect(tailLines(['a'], 0)).toEqual([])
    expect(tailLines(['a'], Number.NaN)).toEqual([])
  })
})

describe('logsToText', () => {
  it('joins lines with newlines', () => {
    expect(logsToText(['a', 'b'])).toBe('a\nb')
  })
})
