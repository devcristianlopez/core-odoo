/**
 * Clipboard helper with a fallback for non-secure contexts (plain HTTP on a
 * LAN host, where `navigator.clipboard` is unavailable).
 */
export async function copyText(value: string): Promise<void> {
  try {
    if (typeof navigator !== 'undefined' && navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(value)
      return
    }
  } catch {
    // Fall back to a temporary textarea below.
  }

  if (typeof document === 'undefined') throw new Error('Clipboard is unavailable')
  const textarea = document.createElement('textarea')
  textarea.value = value
  textarea.setAttribute('readonly', '')
  textarea.style.position = 'fixed'
  textarea.style.top = '-1000px'
  textarea.style.opacity = '0'
  document.body.appendChild(textarea)
  textarea.select()
  try {
    const copied = document.execCommand('copy')
    if (!copied) throw new Error('Copy command failed')
  } finally {
    document.body.removeChild(textarea)
  }
}
