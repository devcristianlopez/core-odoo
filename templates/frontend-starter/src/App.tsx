/**
 * Copyright 2026 Core Odoo contributors
 * SPDX-License-Identifier: Apache-2.0
 */
import { useCallback, useEffect, useState, type FormEvent } from 'react'

import { client, RESOURCE, type ResourceRecord } from './api'

const COLUMNS = ['name', 'nickname', 'email', 'phone', 'city'] as const

function displayValue(record: ResourceRecord, field: string): string {
  const value = record[field]
  if (value === null || value === undefined || value === '') return '—'
  return String(value)
}

export default function App(): JSX.Element {
  const [records, setRecords] = useState<ResourceRecord[]>([])
  const [name, setName] = useState('')
  const [nickname, setNickname] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async (): Promise<void> => {
    try {
      setError(null)
      setRecords(await client.list({ limit: 100, order: 'name asc' }))
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unknown error')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const handleSubmit = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault()
    if (!name.trim()) return
    setSaving(true)
    setError(null)
    try {
      await client.create({ name: name.trim(), nickname: nickname.trim() || null })
      setName('')
      setNickname('')
      await refresh()
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unknown error')
    } finally {
      setSaving(false)
    }
  }

  return (
    <main className="page">
      <header className="page__header">
        <p className="eyebrow">Core Odoo</p>
        <h1>{RESOURCE}</h1>
        <p className="muted">Vite + React + TypeScript frontend talking to the BFF gateway.</p>
      </header>

      <section className="card">
        <h2>New record</h2>
        <form className="form" onSubmit={(event) => void handleSubmit(event)}>
          <label>
            Name
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Ada Lovelace"
              required
            />
          </label>
          <label>
            Nickname
            <input
              value={nickname}
              onChange={(event) => setNickname(event.target.value)}
              placeholder="ada"
            />
          </label>
          <button type="submit" disabled={saving}>
            {saving ? 'Saving…' : 'Create'}
          </button>
        </form>
        {error ? <p className="error" role="alert">{error}</p> : null}
      </section>

      <section className="card">
        <h2>Records {loading ? '' : `(${records.length})`}</h2>
        {loading ? (
          <p className="muted">Loading…</p>
        ) : records.length === 0 ? (
          <p className="muted">No records yet.</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  {COLUMNS.map((column) => (
                    <th key={column}>{column}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {records.map((record) => (
                  <tr key={record.id}>
                    {COLUMNS.map((column) => (
                      <td key={column}>{displayValue(record, column)}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  )
}
