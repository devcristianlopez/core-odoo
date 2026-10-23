/**
 * Copyright 2026 Core Odoo contributors
 * SPDX-License-Identifier: Apache-2.0
 */
import { useCallback, useEffect, useState, type FormEvent } from 'react'

import { createContact, listContacts, type Contact } from './api'

export default function App(): JSX.Element {
  const [contacts, setContacts] = useState<Contact[]>([])
  const [name, setName] = useState('')
  const [nickname, setNickname] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async (): Promise<void> => {
    try {
      setError(null)
      setContacts(await listContacts())
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
      await createContact({
        name: name.trim(),
        nickname: nickname.trim() || null,
      })
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
      <header>
        <p className="eyebrow">Core Odoo · E2E fixture</p>
        <h1>Contacts</h1>
        <p className="muted">
          Lists <code>res.partner</code> through the gateway and creates records with a nickname.
        </p>
      </header>

      <section className="card">
        <h2>New contact</h2>
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
            {saving ? 'Creating…' : 'Create contact'}
          </button>
        </form>
        {error ? <p className="error" role="alert">{error}</p> : null}
      </section>

      <section className="card">
        <h2>Contacts {loading ? '' : `(${contacts.length})`}</h2>
        {loading ? (
          <p className="muted">Loading…</p>
        ) : contacts.length === 0 ? (
          <p className="muted">No contacts yet.</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Nickname</th>
                  <th>Email</th>
                  <th>Phone</th>
                  <th>City</th>
                </tr>
              </thead>
              <tbody>
                {contacts.map((contact) => (
                  <tr key={contact.id}>
                    <td>{contact.name || '—'}</td>
                    <td>{contact.nickname || '—'}</td>
                    <td>{contact.email || '—'}</td>
                    <td>{contact.phone || '—'}</td>
                    <td>{contact.city || '—'}</td>
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
