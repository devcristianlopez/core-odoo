import { beforeEach } from 'vitest'

/**
 * Node 22+ exposes a global `localStorage` that is only usable when the process
 * is started with `--localstorage-file`. Vitest's jsdom environment inherits
 * that global, so `window.localStorage` can be `undefined` even though the DOM
 * is available. Install a small in-memory Storage implementation instead of
 * relying on the runtime flag.
 */
class MemoryStorage implements Storage {
  private items = new Map<string, string>()

  get length(): number {
    return this.items.size
  }

  clear(): void {
    this.items.clear()
  }

  getItem(key: string): string | null {
    return this.items.get(String(key)) ?? null
  }

  key(index: number): string | null {
    return Array.from(this.items.keys())[index] ?? null
  }

  removeItem(key: string): void {
    this.items.delete(String(key))
  }

  setItem(key: string, value: string): void {
    this.items.set(String(key), String(value))
  }
}

function installLocalStorage(): void {
  // Replace the property without reading it: reading Node's getter emits an
  // ExperimentalWarning when no `--localstorage-file` was supplied.
  const storage = new MemoryStorage()
  Object.defineProperty(globalThis, 'localStorage', {
    configurable: true,
    get: () => storage,
  })
}

installLocalStorage()

beforeEach(() => {
  globalThis.localStorage.clear()
})
