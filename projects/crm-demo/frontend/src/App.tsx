/**
 * Copyright 2026 Core Odoo contributors
 * SPDX-License-Identifier: Apache-2.0
 */
import { useCallback, useEffect, useState, type FormEvent } from 'react'

import {
  LOGIN_KEY,
  TOKEN_KEY,
  createContact,
  createLead,
  deleteContact,
  deleteLead,
  listContacts,
  listLeads,
  loginRequest,
  updateContact,
  updateLead,
  type Contact,
  type ContactInput,
  type Lead,
  type LeadInput,
  type Stage,
} from './api'

type Lang = 'es' | 'en'
type Tab = 'leads' | 'contacts'

const STRINGS = {
  es: {
    appName: 'CRM Demo',
    tagline: 'Leads, contactos y embudo simple sobre Odoo 20',
    loginTitle: 'Entrar al CRM',
    loginHint: 'Usa el usuario de Odoo. En este demo: admin / admin.',
    login: 'Usuario',
    password: 'Contraseña',
    signIn: 'Entrar',
    signingIn: 'Entrando…',
    logout: 'Salir',
    leads: 'Leads',
    contacts: 'Contactos',
    newLead: 'Nuevo lead',
    editLead: 'Editar lead',
    newContact: 'Nuevo contacto',
    editContact: 'Editar contacto',
    name: 'Nombre',
    contact: 'Contacto',
    email: 'Email',
    phone: 'Teléfono',
    city: 'Ciudad',
    stage: 'Etapa',
    revenue: 'Ingreso esperado',
    notes: 'Notas',
    save: 'Guardar',
    saving: 'Guardando…',
    cancel: 'Cancelar',
    edit: 'Editar',
    delete: 'Borrar',
    actions: 'Acciones',
    emptyLeads: 'No hay leads todavía. Crea el primero.',
    emptyContacts: 'No hay contactos todavía. Crea el primero.',
    loading: 'Cargando…',
    confirmDelete: '¿Confirmas que quieres borrar este registro?',
    language: 'Idioma',
    total: 'Total',
    pipeline: 'Pipeline',
    stageNew: 'Nuevo',
    stageContacted: 'Contactado',
    stageProposal: 'Propuesta',
    stageWon: 'Ganado',
    stageLost: 'Perdido',
    session: 'Sesión',
    hint: 'Los datos se guardan en Odoo a través del gateway.',
    refresh: 'Actualizar',
  },
  en: {
    appName: 'CRM Demo',
    tagline: 'A simple leads, contacts and pipeline demo on Odoo 20',
    loginTitle: 'Sign in to CRM',
    loginHint: 'Use an Odoo user. Demo credentials: admin / admin.',
    login: 'Login',
    password: 'Password',
    signIn: 'Sign in',
    signingIn: 'Signing in…',
    logout: 'Sign out',
    leads: 'Leads',
    contacts: 'Contacts',
    newLead: 'New lead',
    editLead: 'Edit lead',
    newContact: 'New contact',
    editContact: 'Edit contact',
    name: 'Name',
    contact: 'Contact',
    email: 'Email',
    phone: 'Phone',
    city: 'City',
    stage: 'Stage',
    revenue: 'Expected revenue',
    notes: 'Notes',
    save: 'Save',
    saving: 'Saving…',
    cancel: 'Cancel',
    edit: 'Edit',
    delete: 'Delete',
    actions: 'Actions',
    emptyLeads: 'No leads yet. Create the first one.',
    emptyContacts: 'No contacts yet. Create the first one.',
    loading: 'Loading…',
    confirmDelete: 'Delete this record?',
    language: 'Language',
    total: 'Total',
    pipeline: 'Pipeline',
    stageNew: 'New',
    stageContacted: 'Contacted',
    stageProposal: 'Proposal',
    stageWon: 'Won',
    stageLost: 'Lost',
    session: 'Session',
    hint: 'Data is stored in Odoo through the gateway.',
    refresh: 'Refresh',
  },
} as const

type Copy = { [K in keyof typeof STRINGS.es]: string }
type LeadForm = {
  name: string
  contact_name: string
  email: string
  phone: string
  stage: Stage
  expected_revenue: string
  notes: string
}
type ContactForm = { name: string; email: string; phone: string; city: string }

const EMPTY_LEAD: LeadForm = {
  name: '',
  contact_name: '',
  email: '',
  phone: '',
  stage: 'new',
  expected_revenue: '',
  notes: '',
}
const EMPTY_CONTACT: ContactForm = { name: '', email: '', phone: '', city: '' }
const STAGES: Stage[] = ['new', 'contacted', 'proposal', 'won', 'lost']

function stageLabel(text: Copy, stage: Stage): string {
  const labels: Record<Stage, string> = {
    new: text.stageNew,
    contacted: text.stageContacted,
    proposal: text.stageProposal,
    won: text.stageWon,
    lost: text.stageLost,
  }
  return labels[stage]
}

function message(error: unknown): string {
  return error instanceof Error ? error.message : 'Unexpected error'
}

export default function App(): JSX.Element {
  const [lang, setLang] = useState<Lang>(() => (localStorage.getItem('crm_demo_lang') as Lang) || 'es')
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(TOKEN_KEY))
  const [loginName, setLoginName] = useState<string>(() => localStorage.getItem(LOGIN_KEY) ?? '')
  const text = STRINGS[lang]

  const changeLang = (next: Lang): void => {
    setLang(next)
    localStorage.setItem('crm_demo_lang', next)
  }

  const handleLogin = (nextToken: string, nextLogin: string): void => {
    localStorage.setItem(TOKEN_KEY, nextToken)
    localStorage.setItem(LOGIN_KEY, nextLogin)
    setToken(nextToken)
    setLoginName(nextLogin)
  }

  const handleLogout = (): void => {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(LOGIN_KEY)
    setToken(null)
    setLoginName('')
  }

  if (!token) {
    return <Login text={text} lang={lang} onLang={changeLang} onLogin={handleLogin} />
  }

  return (
    <Workspace
      token={token}
      loginName={loginName}
      text={text}
      lang={lang}
      onLang={changeLang}
      onLogout={handleLogout}
    />
  )
}

function Login({
  text,
  lang,
  onLang,
  onLogin,
}: {
  text: Copy
  lang: Lang
  onLang: (lang: Lang) => void
  onLogin: (token: string, login: string) => void
}): JSX.Element {
  const [login, setLogin] = useState('admin')
  const [password, setPassword] = useState('admin')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const accessToken = await loginRequest(login.trim(), password)
      onLogin(accessToken, login.trim())
    } catch (caught) {
      setError(message(caught))
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="login-shell">
      <div className="login-glow" aria-hidden="true" />
      <section className="login-card">
        <div className="brand-row">
          <div className="brand-mark">CD</div>
          <div>
            <p className="eyebrow">Core Odoo · Odoo 20</p>
            <h1>{text.appName}</h1>
          </div>
          <LangToggle lang={lang} onLang={onLang} />
        </div>
        <p className="muted">{text.tagline}</p>
        <form className="stack" onSubmit={(event) => void submit(event)}>
          <label className="field">
            <span>{text.login}</span>
            <input value={login} onChange={(event) => setLogin(event.target.value)} autoComplete="username" required />
          </label>
          <label className="field">
            <span>{text.password}</span>
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="current-password"
              required
            />
          </label>
          <button className="btn primary wide" type="submit" disabled={busy}>
            {busy ? text.signingIn : text.signIn}
          </button>
          {error && <p className="error">{error}</p>}
          <p className="hint">{text.loginHint}</p>
        </form>
      </section>
    </main>
  )
}

function LangToggle({ lang, onLang }: { lang: Lang; onLang: (lang: Lang) => void }): JSX.Element {
  return (
    <div className="lang-toggle" role="group" aria-label="Language">
      <button className={lang === 'es' ? 'active' : ''} onClick={() => onLang('es')} type="button">
        ES
      </button>
      <button className={lang === 'en' ? 'active' : ''} onClick={() => onLang('en')} type="button">
        EN
      </button>
    </div>
  )
}

function Workspace({
  token,
  loginName,
  text,
  lang,
  onLang,
  onLogout,
}: {
  token: string
  loginName: string
  text: Copy
  lang: Lang
  onLang: (lang: Lang) => void
  onLogout: () => void
}): JSX.Element {
  const [tab, setTab] = useState<Tab>('leads')
  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand-row">
          <div className="brand-mark small">CD</div>
          <div>
            <strong>{text.appName}</strong>
            <p className="muted tiny">{text.tagline}</p>
          </div>
        </div>
        <nav className="tabs">
          <button className={tab === 'leads' ? 'active' : ''} onClick={() => setTab('leads')} type="button">
            {text.leads}
          </button>
          <button
            className={tab === 'contacts' ? 'active' : ''}
            onClick={() => setTab('contacts')}
            type="button"
          >
            {text.contacts}
          </button>
        </nav>
        <div className="session">
          <span className="pill">{text.session}: {loginName}</span>
          <LangToggle lang={lang} onLang={onLang} />
          <button className="btn ghost" onClick={onLogout} type="button">
            {text.logout}
          </button>
        </div>
      </header>
      <main className="content">
        {tab === 'leads' ? (
          <LeadsPanel token={token} text={text} />
        ) : (
          <ContactsPanel token={token} text={text} />
        )}
        <p className="hint center">{text.hint}</p>
      </main>
    </div>
  )
}

function LeadsPanel({ token, text }: { token: string; text: Copy }): JSX.Element {
  const [leads, setLeads] = useState<Lead[]>([])
  const [form, setForm] = useState<LeadForm>(EMPTY_LEAD)
  const [editing, setEditing] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async (): Promise<void> => {
    setLoading(true)
    setError(null)
    try {
      setLeads(await listLeads(token))
    } catch (caught) {
      setError(message(caught))
    } finally {
      setLoading(false)
    }
  }, [token])

  useEffect(() => {
    void load()
  }, [load])

  const setField = <K extends keyof LeadForm>(key: K, value: LeadForm[K]): void => {
    setForm((current) => ({ ...current, [key]: value }))
  }

  const submit = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault()
    if (!form.name.trim()) return
    setSaving(true)
    setError(null)
    const values: LeadInput = {
      name: form.name.trim(),
      contact_name: form.contact_name.trim(),
      email: form.email.trim(),
      phone: form.phone.trim(),
      stage: form.stage,
      expected_revenue: Number(form.expected_revenue) || 0,
      notes: form.notes.trim(),
    }
    try {
      if (editing === null) await createLead(token, values)
      else await updateLead(token, editing, values)
      setForm(EMPTY_LEAD)
      setEditing(null)
      await load()
    } catch (caught) {
      setError(message(caught))
    } finally {
      setSaving(false)
    }
  }

  const edit = (lead: Lead): void => {
    setEditing(lead.id)
    setForm({
      name: lead.name,
      contact_name: lead.contact_name || '',
      email: lead.email || '',
      phone: lead.phone || '',
      stage: lead.stage,
      expected_revenue: lead.expected_revenue ? String(lead.expected_revenue) : '',
      notes: lead.notes || '',
    })
  }

  const remove = async (id: number): Promise<void> => {
    if (!window.confirm(text.confirmDelete)) return
    try {
      await deleteLead(token, id)
      if (editing === id) {
        setEditing(null)
        setForm(EMPTY_LEAD)
      }
      await load()
    } catch (caught) {
      setError(message(caught))
    }
  }

  const changeStage = async (id: number, stage: Stage): Promise<void> => {
    try {
      await updateLead(token, id, { stage })
      await load()
    } catch (caught) {
      setError(message(caught))
    }
  }

  const open = leads.filter((lead) => lead.stage !== 'won' && lead.stage !== 'lost').length
  const total = leads.reduce((sum, lead) => sum + Number(lead.expected_revenue || 0), 0)

  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <p className="eyebrow">{text.pipeline}</p>
          <h2>{text.leads}</h2>
        </div>
        <button className="btn ghost" onClick={() => void load()} type="button" disabled={loading}>
          {text.refresh}
        </button>
      </div>
      <div className="stats">
        <div className="stat"><span>{text.total}</span><strong>{leads.length}</strong></div>
        <div className="stat"><span>{text.pipeline}</span><strong>{open}</strong></div>
        <div className="stat"><span>{text.revenue}</span><strong>{total.toLocaleString()}</strong></div>
      </div>

      <form className="form-grid" onSubmit={(event) => void submit(event)}>
        <label className="field"><span>{text.name}</span>
          <input value={form.name} onChange={(event) => setField('name', event.target.value)} required />
        </label>
        <label className="field"><span>{text.contact}</span>
          <input value={form.contact_name} onChange={(event) => setField('contact_name', event.target.value)} />
        </label>
        <label className="field"><span>{text.email}</span>
          <input type="email" value={form.email} onChange={(event) => setField('email', event.target.value)} />
        </label>
        <label className="field"><span>{text.phone}</span>
          <input value={form.phone} onChange={(event) => setField('phone', event.target.value)} />
        </label>
        <label className="field"><span>{text.stage}</span>
          <select value={form.stage} onChange={(event) => setField('stage', event.target.value as Stage)}>
            {STAGES.map((stage) => <option key={stage} value={stage}>{stageLabel(text, stage)}</option>)}
          </select>
        </label>
        <label className="field"><span>{text.revenue}</span>
          <input type="number" min="0" step="0.01" value={form.expected_revenue} onChange={(event) => setField('expected_revenue', event.target.value)} />
        </label>
        <label className="field wide"><span>{text.notes}</span>
          <textarea rows={2} value={form.notes} onChange={(event) => setField('notes', event.target.value)} />
        </label>
        <div className="form-actions">
          <button className="btn primary" type="submit" disabled={saving}>
            {saving ? text.saving : editing === null ? text.newLead : text.save}
          </button>
          {editing !== null && (
            <button className="btn ghost" type="button" onClick={() => { setEditing(null); setForm(EMPTY_LEAD) }}>
              {text.cancel}
            </button>
          )}
        </div>
      </form>

      {error && <p className="error">{error}</p>}
      {loading ? <p className="empty">{text.loading}</p> : leads.length === 0 ? (
        <p className="empty">{text.emptyLeads}</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead><tr><th>{text.name}</th><th>{text.contact}</th><th>{text.stage}</th><th>{text.revenue}</th><th>{text.actions}</th></tr></thead>
            <tbody>
              {leads.map((lead) => (
                <tr key={lead.id}>
                  <td><strong>{lead.name}</strong><div className="muted tiny">{lead.email || lead.phone || '—'}</div></td>
                  <td>{lead.contact_name || '—'}</td>
                  <td>
                    <select className={`stage ${lead.stage}`} value={lead.stage} onChange={(event) => void changeStage(lead.id, event.target.value as Stage)}>
                      {STAGES.map((stage) => <option key={stage} value={stage}>{stageLabel(text, stage)}</option>)}
                    </select>
                  </td>
                  <td>{Number(lead.expected_revenue || 0).toLocaleString()}</td>
                  <td className="row-actions">
                    <button className="btn tiny" onClick={() => edit(lead)} type="button">{text.edit}</button>
                    <button className="btn tiny danger" onClick={() => void remove(lead.id)} type="button">{text.delete}</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

function ContactsPanel({ token, text }: { token: string; text: Copy }): JSX.Element {
  const [contacts, setContacts] = useState<Contact[]>([])
  const [form, setForm] = useState<ContactForm>(EMPTY_CONTACT)
  const [editing, setEditing] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async (): Promise<void> => {
    setLoading(true)
    setError(null)
    try {
      setContacts(await listContacts(token))
    } catch (caught) {
      setError(message(caught))
    } finally {
      setLoading(false)
    }
  }, [token])

  useEffect(() => {
    void load()
  }, [load])

  const setField = (key: keyof ContactForm, value: string): void => {
    setForm((current) => ({ ...current, [key]: value }))
  }

  const submit = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault()
    if (!form.name.trim()) return
    setSaving(true)
    setError(null)
    const values: ContactInput = {
      name: form.name.trim(),
      email: form.email.trim(),
      phone: form.phone.trim(),
      city: form.city.trim(),
    }
    try {
      if (editing === null) await createContact(token, values)
      else await updateContact(token, editing, values)
      setForm(EMPTY_CONTACT)
      setEditing(null)
      await load()
    } catch (caught) {
      setError(message(caught))
    } finally {
      setSaving(false)
    }
  }

  const edit = (contact: Contact): void => {
    setEditing(contact.id)
    setForm({
      name: contact.name,
      email: contact.email || '',
      phone: contact.phone || '',
      city: contact.city || '',
    })
  }

  const remove = async (id: number): Promise<void> => {
    if (!window.confirm(text.confirmDelete)) return
    try {
      await deleteContact(token, id)
      if (editing === id) {
        setEditing(null)
        setForm(EMPTY_CONTACT)
      }
      await load()
    } catch (caught) {
      setError(message(caught))
    }
  }

  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <p className="eyebrow">res.partner</p>
          <h2>{text.contacts}</h2>
        </div>
        <button className="btn ghost" onClick={() => void load()} type="button" disabled={loading}>
          {text.refresh}
        </button>
      </div>

      <form className="form-grid" onSubmit={(event) => void submit(event)}>
        <label className="field"><span>{text.name}</span>
          <input value={form.name} onChange={(event) => setField('name', event.target.value)} required />
        </label>
        <label className="field"><span>{text.email}</span>
          <input type="email" value={form.email} onChange={(event) => setField('email', event.target.value)} />
        </label>
        <label className="field"><span>{text.phone}</span>
          <input value={form.phone} onChange={(event) => setField('phone', event.target.value)} />
        </label>
        <label className="field"><span>{text.city}</span>
          <input value={form.city} onChange={(event) => setField('city', event.target.value)} />
        </label>
        <div className="form-actions">
          <button className="btn primary" type="submit" disabled={saving}>
            {saving ? text.saving : editing === null ? text.newContact : text.save}
          </button>
          {editing !== null && (
            <button className="btn ghost" type="button" onClick={() => { setEditing(null); setForm(EMPTY_CONTACT) }}>
              {text.cancel}
            </button>
          )}
        </div>
      </form>

      {error && <p className="error">{error}</p>}
      {loading ? <p className="empty">{text.loading}</p> : contacts.length === 0 ? (
        <p className="empty">{text.emptyContacts}</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead><tr><th>{text.name}</th><th>{text.email}</th><th>{text.phone}</th><th>{text.city}</th><th>{text.actions}</th></tr></thead>
            <tbody>
              {contacts.map((contact) => (
                <tr key={contact.id}>
                  <td><strong>{contact.name}</strong></td>
                  <td>{contact.email || '—'}</td>
                  <td>{contact.phone || '—'}</td>
                  <td>{contact.city || '—'}</td>
                  <td className="row-actions">
                    <button className="btn tiny" onClick={() => edit(contact)} type="button">{text.edit}</button>
                    <button className="btn tiny danger" onClick={() => void remove(contact.id)} type="button">{text.delete}</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
