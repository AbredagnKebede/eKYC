const TOKEN_KEY = 'bank_portal_token'
const META_KEY = 'bank_portal_meta'

export type PortalMeta = {
  token: string
  bank_id: string
  role: string
  email: string
}

function apiBase(): string {
  const raw = process.env.NEXT_PUBLIC_API_BASE_URL || ''
  return raw.replace(/\/$/, '')
}

export function loadMeta(): PortalMeta | null {
  if (typeof window === 'undefined') return null
  try {
    const raw = localStorage.getItem(META_KEY)
    return raw ? (JSON.parse(raw) as PortalMeta) : null
  } catch {
    return null
  }
}

export function saveMeta(meta: PortalMeta) {
  localStorage.setItem(TOKEN_KEY, meta.token)
  localStorage.setItem(META_KEY, JSON.stringify(meta))
}

export function clearMeta() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(META_KEY)
}

async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const meta = loadMeta()
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(init.headers as Record<string, string> | undefined),
  }
  if (meta?.token) headers.Authorization = `Bearer ${meta.token}`
  const url = `${apiBase()}${path}`
  const res = await fetch(url, { ...init, headers })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = body.detail || body.title || JSON.stringify(body)
    } catch {
      /* ignore */
    }
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

export const portalApi = {
  login: (email: string, password: string, bank_id: string) =>
    api<{ token: string; bank_id: string; role: string; email: string; expires_in: number }>(
      '/v1/bank-portal/auth/login',
      { method: 'POST', body: JSON.stringify({ email, password, bank_id }) },
    ),
  dashboard: () =>
    api<{
      bank_id: string
      outbound_count: number
      inbound_count: number
      ff_outbound: boolean
      ff_inbound: boolean
    }>('/v1/bank-portal/dashboard'),
  settings: () =>
    api<{ bank_id: string; ff_outbound: boolean; ff_inbound: boolean }>(
      '/v1/bank-portal/settings',
    ),
  patchSettings: (body: { ff_outbound?: boolean; ff_inbound?: boolean }) =>
    api<{ bank_id: string; ff_outbound: boolean; ff_inbound: boolean }>(
      '/v1/bank-portal/settings',
      { method: 'PATCH', body: JSON.stringify(body) },
    ),
  outbound: () => api<QueueItem[]>('/v1/bank-portal/queues/outbound'),
  inbound: () => api<QueueItem[]>('/v1/bank-portal/queues/inbound'),
  sendOutbound: (id: string, edited_fields?: Record<string, unknown>) =>
    api<QueueItem>(`/v1/bank-portal/queues/outbound/${id}/send`, {
      method: 'POST',
      body: JSON.stringify({ edited_fields }),
    }),
  releaseInbound: (
    id: string,
    body: {
      status: string
      account_number?: string
      bank_reference?: string
      reject_reason?: string
    },
  ) =>
    api<QueueItem>(`/v1/bank-portal/queues/inbound/${id}/release`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  staff: () => api<StaffItem[]>('/v1/bank-portal/staff'),
  inviteStaff: (body: { email: string; password: string; role: string }) =>
    api<StaffItem>('/v1/bank-portal/staff', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  revokeStaff: (id: string) =>
    api<StaffItem>(`/v1/bank-portal/staff/${id}/revoke`, { method: 'POST' }),
  audit: () => api<AuditItem[]>('/v1/bank-portal/audit'),
}

export type QueueItem = {
  application_id: string
  user_ref: string
  bank_id: string
  tier: string
  status: string
  created_at: string
  updated_at: string
  account_number?: string | null
  bank_reference?: string | null
  error_message?: string | null
  dynamic_fields?: Record<string, unknown> | null
}

export type StaffItem = {
  id: string
  email: string
  role: string
  active: boolean
  created_at: string
}

export type AuditItem = {
  id: number
  timestamp: string
  actor_type: string
  actor_id: string
  action: string
  application_id?: string | null
}
