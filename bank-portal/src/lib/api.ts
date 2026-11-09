const TOKEN_KEY = 'bank_portal_token'
const META_KEY = 'bank_portal_meta'
const PLATFORM_TOKEN_KEY = 'platform_portal_token'
const PLATFORM_META_KEY = 'platform_portal_meta'

export type PortalMeta = {
  token: string
  bank_id: string
  role: string
  email: string
}

export type PlatformMeta = {
  token: string
  email: string
  role: string
}

export type PublicBank = {
  bank_id: string
  bank_name: string
  short_code?: string | null
  hq_city?: string | null
  supported_tiers: string[]
}

export type PartnerBankRow = {
  bank_id: string
  bank_name: string
  short_code: string
  hq_city?: string | null
  supported_tiers: string[]
  active: boolean
  use_legacy_awash?: boolean
  created_at?: string | null
  updated_at?: string | null
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

export function loadPlatformMeta(): PlatformMeta | null {
  if (typeof window === 'undefined') return null
  try {
    const raw = localStorage.getItem(PLATFORM_META_KEY)
    return raw ? (JSON.parse(raw) as PlatformMeta) : null
  } catch {
    return null
  }
}

export function savePlatformMeta(meta: PlatformMeta) {
  localStorage.setItem(PLATFORM_TOKEN_KEY, meta.token)
  localStorage.setItem(PLATFORM_META_KEY, JSON.stringify(meta))
}

export function clearPlatformMeta() {
  localStorage.removeItem(PLATFORM_TOKEN_KEY)
  localStorage.removeItem(PLATFORM_META_KEY)
}

async function requestJson<T>(
  path: string,
  init: RequestInit = {},
  token?: string | null,
): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(init.headers as Record<string, string> | undefined),
  }
  if (token) headers.Authorization = `Bearer ${token}`
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

async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  return requestJson<T>(path, init, loadMeta()?.token)
}

async function platformApiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  return requestJson<T>(path, init, loadPlatformMeta()?.token)
}

export async function fetchPublicBanks(): Promise<PublicBank[]> {
  return requestJson<PublicBank[]>('/v1/banks')
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

export const platformApi = {
  login: (email: string, password: string) =>
    requestJson<{ token: string; email: string; role: string; expires_in: number }>(
      '/v1/platform/auth/login',
      { method: 'POST', body: JSON.stringify({ email, password }) },
    ),
  banks: () => platformApiRequest<PartnerBankRow[]>('/v1/platform/banks'),
  createBank: (body: {
    bank_id: string
    bank_name: string
    short_code: string
    hq_city?: string
    supported_tiers?: string[]
    super_admin_email?: string
  }) =>
    platformApiRequest<{
      bank: PartnerBankRow
      super_admin_email: string
      temporary_password: string
    }>('/v1/platform/banks', { method: 'POST', body: JSON.stringify(body) }),
  patchBank: (
    bank_id: string,
    body: {
      bank_name?: string
      short_code?: string
      hq_city?: string
      supported_tiers?: string[]
      active?: boolean
    },
  ) =>
    platformApiRequest<PartnerBankRow>(`/v1/platform/banks/${bank_id}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  resetSuperAdmin: (bank_id: string, email?: string) =>
    platformApiRequest<{
      bank_id: string
      super_admin_email: string
      temporary_password: string
    }>(`/v1/platform/banks/${bank_id}/reset-super-admin`, {
      method: 'POST',
      body: JSON.stringify({ confirm: true, email }),
    }),
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
