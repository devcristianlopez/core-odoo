import { describe, expect, it } from 'vitest'
import en from './en'
import es from './es'

type Catalog = { [key: string]: string | Catalog }

function flattenKeys(catalog: Catalog, prefix = ''): string[] {
  const keys: string[] = []
  for (const [key, value] of Object.entries(catalog)) {
    const path = prefix === '' ? key : `${prefix}.${key}`
    if (typeof value === 'string') keys.push(path)
    else keys.push(...flattenKeys(value, path))
  }
  return keys.sort()
}

describe('i18n catalogs', () => {
  it('have exactly the same keys in English and Spanish', () => {
    const enKeys = flattenKeys(en as unknown as Catalog)
    const esKeys = flattenKeys(es as unknown as Catalog)
    expect(esKeys.filter((key) => !enKeys.includes(key))).toEqual([])
    expect(enKeys.filter((key) => !esKeys.includes(key))).toEqual([])
  })

  it('do not contain empty translations', () => {
    const collect = (catalog: Catalog, prefix = ''): Array<[string, string]> => {
      const entries: Array<[string, string]> = []
      for (const [key, value] of Object.entries(catalog)) {
        const path = prefix === '' ? key : `${prefix}.${key}`
        if (typeof value === 'string') entries.push([path, value])
        else entries.push(...collect(value, path))
      }
      return entries
    }
    for (const [key, value] of [...collect(en as unknown as Catalog), ...collect(es as unknown as Catalog)]) {
      expect(value.trim(), key).not.toBe('')
    }
  })
})
