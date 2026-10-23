const ESC = String.fromCharCode(27)
const BEL = String.fromCharCode(7)
const ANSI_CSI = new RegExp(`${ESC}\\[[0-9;?]*[ -/]*[@-~]`, 'g')
const ANSI_OSC = new RegExp(`${ESC}\\][^${BEL}]*(?:${BEL}|${ESC}\\\\)`, 'g')
const ANSI_SINGLE = new RegExp(`${ESC}[@-_]`, 'g')

export function stripAnsi(value: string): string {
  return value.replace(ANSI_OSC, '').replace(ANSI_CSI, '').replace(ANSI_SINGLE, '')
}

export function splitLogLines(value: string | null | undefined): string[] {
  if (!value) return []
  return stripAnsi(value)
    .replace(/\r\n/g, '\n')
    .split('\n')
    .filter((line, index, lines) => line !== '' || index < lines.length - 1)
}

export function tailLines(lines: string[], count: number): string[] {
  if (!Number.isFinite(count) || count <= 0) return []
  return lines.slice(-Math.floor(count))
}

export function filterLogLines(lines: string[], query: string): string[] {
  const trimmed = query.trim()
  if (trimmed === '') return lines
  const needle = trimmed.toLowerCase()
  return lines.filter((line) => line.toLowerCase().includes(needle))
}

export function logsToText(lines: string[]): string {
  return lines.join('\n')
}
