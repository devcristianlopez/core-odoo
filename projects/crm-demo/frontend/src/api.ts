/**
 * Copyright 2026 Core Odoo contributors
 * SPDX-License-Identifier: Apache-2.0
 */
export type Stage = 'new' | 'contacted' | 'proposal' | 'won' | 'lost'

export interface Lead {
  id: number
  name: string
  contact_name: string | false
  email: string | false
  phone: string | false
  stage: Stage
  expected_revenue: number
  notes: string | false
}

export interface LeadInput {
  name: string
  contact_name: string
  email: string
  phone: string
  stage: Stage
  expected_revenue: number
  notes: string
}

export interface Contact {
  id: number
  name: string
  email: string | false
  phone: string | false
  city: string | false
}

export interface ContactInput {
  name: string
  email: string
  phone: string
  city: string
}

export const TOKEN_KEY = 'crm_demo_token'
export const LOGIN_KEY = 'crm_demo_login'

interface RequestOptions {
  method?: string
  body?: unknown
  token?: string
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (options.body !== undefined) headers['Content-Type'] = 'application/json'
  if (options.token) headers.Authorization = `Bearer ${options.token}`
  const response = await fetch(path, {
    method: options.method ?? 'GET',
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  })
  const payload = (await response.json().catch(() => ({}))) as Record<string, unknown>
  if (!response.ok) {
    const detail = payload.detail
    const error = payload.error as { message?: string } | undefined
    throw new Error(
      (typeof detail === 'string' && detail) ||
        error?.message ||
        `HTTP ${response.status}`,
    )
  }
  return payload as T
}

export async function loginRequest(login: string, password: string): Promise<string> {
  const data = await request<{ access_token: string }>('/auth/login', {
    method: 'POST',
    body: { login, password },
  })
  return data.access_token
}

export function listLeads(token: string): Promise<Lead[]> {
  return request<Lead[]>('/api/leads?limit=200', { token })
}

export function createLead(token: string, values: LeadInput): Promise<{ id: number }> {
  return request<{ id: number }>('/api/leads', { method: 'POST', body: values, token })
}

export function updateLead(token: string, id: number, values: Partial<LeadInput>): Promise<unknown> {
  return request(`/api/leads/${id}`, { method: 'PATCH', body: values, token })
}

export function deleteLead(token: string, id: number): Promise<unknown> {
  return request(`/api/leads/${id}`, { method: 'DELETE', token })
}

export function listContacts(token: string): Promise<Contact[]> {
  return request<Contact[]>('/api/contacts?limit=200', { token })
}

export function createContact(token: string, values: ContactInput): Promise<{ id: number }> {
  return request<{ id: number }>('/api/contacts', { method: 'POST', body: values, token })
}

export function updateContact(
  token: string,
  id: number,
  values: Partial<ContactInput>,
): Promise<unknown> {
  return request(`/api/contacts/${id}`, { method: 'PATCH', body: values, token })
}

export function deleteContact(token: string, id: number): Promise<unknown> {
  return request(`/api/contacts/${id}`, { method: 'DELETE', token })
}
