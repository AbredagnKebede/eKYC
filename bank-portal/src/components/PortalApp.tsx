'use client'

import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import {
  clearMeta,
  loadMeta,
  portalApi,
  saveMeta,
} from '@/lib/api'
import type { AuditItem, QueueItem, StaffItem } from '@/lib/api'

type Tab = 'dashboard' | 'outbound' | 'inbound' | 'settings' | 'staff' | 'audit'

const BANKS = [
  'bank_cbe',
  'bank_awash',
  'bank_abyssinia',
  'bank_dashen',
  'bank_wegagen',
  'bank_hibret',
  'bank_coop',
  'bank_nib',
]

export default function PortalApp() {
  const [meta, setMeta] = useState<ReturnType<typeof loadMeta>>(null)
  const [hydrated, setHydrated] = useState(false)
  const [tab, setTab] = useState<Tab>('dashboard')
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const [email, setEmail] = useState('super@cbe.portal.local')
  const [password, setPassword] = useState('ChangeMeBankPortal1!')
  const [bankId, setBankId] = useState('bank_cbe')

  const [dash, setDash] = useState<{
    outbound_count: number
    inbound_count: number
    ff_outbound: boolean
    ff_inbound: boolean
  } | null>(null)
  const [outbound, setOutbound] = useState<QueueItem[]>([])
  const [inbound, setInbound] = useState<QueueItem[]>([])
  const [ffOut, setFfOut] = useState(true)
  const [ffIn, setFfIn] = useState(true)
  const [staff, setStaff] = useState<StaffItem[]>([])
  const [audit, setAudit] = useState<AuditItem[]>([])
  const [inviteEmail, setInviteEmail] = useState('')
  const [invitePassword, setInvitePassword] = useState('TempPass123!')
  const [inviteRole, setInviteRole] = useState('EMPLOYEE')

  useEffect(() => {
    setMeta(loadMeta())
    setHydrated(true)
  }, [])

  const canManageSettings = useMemo(
    () => meta?.role === 'SUPER_ADMIN' || meta?.role === 'ADMIN',
    [meta],
  )
  const canManageStaff = canManageSettings

  async function refresh() {
    if (!meta) return
    setError(null)
    try {
      if (tab === 'dashboard') {
        setDash(await portalApi.dashboard())
      } else if (tab === 'outbound') {
        setOutbound(await portalApi.outbound())
      } else if (tab === 'inbound') {
        setInbound(await portalApi.inbound())
      } else if (tab === 'settings') {
        const s = await portalApi.settings()
        setFfOut(s.ff_outbound)
        setFfIn(s.ff_inbound)
      } else if (tab === 'staff' && canManageStaff) {
        setStaff(await portalApi.staff())
      } else if (tab === 'audit' && canManageStaff) {
        setAudit(await portalApi.audit())
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  useEffect(() => {
    if (!hydrated) return
    void refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [meta, tab, hydrated])

  async function onLogin(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const res = await portalApi.login(email, password, bankId)
      const next = {
        token: res.token,
        bank_id: res.bank_id,
        role: res.role,
        email: res.email,
      }
      saveMeta(next)
      setMeta(next)
      setTab('dashboard')
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  function logout() {
    clearMeta()
    setMeta(null)
    setDash(null)
  }

  if (!hydrated) {
    return <div className="app-shell">Loading…</div>
  }

  if (!meta) {
    return (
      <div className="app-shell">
        <div className="brand-mark">Fayda Bank Portal</div>
        <p className="brand-sub">
          Per-bank Fast Forward gates, outbound and inbound queues, and staff RBAC —
          isolated to your institution.
        </p>
        <form className="login-panel" onSubmit={onLogin}>
          <label htmlFor="bank">Bank</label>
          <select id="bank" value={bankId} onChange={(e) => setBankId(e.target.value)}>
            {BANKS.map((b) => (
              <option key={b} value={b}>
                {b}
              </option>
            ))}
          </select>
          <label htmlFor="email">Email</label>
          <input
            id="email"
            type="email"
            autoComplete="username"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
          <label htmlFor="password">Password</label>
          <input
            id="password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
          {error && <p className="err">{error}</p>}
          <div style={{ marginTop: '1.25rem' }}>
            <button className="btn" type="submit" disabled={busy}>
              {busy ? 'Signing in…' : 'Sign in'}
            </button>
          </div>
        </form>
      </div>
    )
  }

  return (
    <div className="app-shell">
      <div className="topbar">
        <div>
          <div className="brand-mark">Fayda Bank Portal</div>
          <p className="brand-sub">
            {meta.bank_id} · {meta.email} · <span className="pill">{meta.role}</span>
          </p>
        </div>
        <button className="btn secondary" type="button" onClick={logout}>
          Sign out
        </button>
      </div>

      <nav className="nav">
        {(
          [
            ['dashboard', 'Dashboard'],
            ['outbound', 'Outbound'],
            ['inbound', 'Inbound'],
            ['settings', 'Settings'],
            ...(canManageStaff
              ? ([
                  ['staff', 'Staff'],
                  ['audit', 'Audit'],
                ] as const)
              : []),
          ] as [Tab, string][]
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            className={tab === id ? 'active' : ''}
            onClick={() => {
              setNotice(null)
              setTab(id)
            }}
          >
            {label}
          </button>
        ))}
      </nav>

      {error && <p className="err">{error}</p>}
      {notice && <p className="ok">{notice}</p>}

      {tab === 'dashboard' && dash && (
        <section>
          <div className="metrics">
            <div className="metric">
              <div className="n">{dash.outbound_count}</div>
              <div>Outbound queue</div>
            </div>
            <div className="metric">
              <div className="n">{dash.inbound_count}</div>
              <div>Inbound queue</div>
            </div>
            <div className="metric">
              <div className="n">{dash.ff_outbound ? 'ON' : 'OFF'}</div>
              <div>FF outbound</div>
            </div>
            <div className="metric">
              <div className="n">{dash.ff_inbound ? 'ON' : 'OFF'}</div>
              <div>FF inbound</div>
            </div>
          </div>
        </section>
      )}

      {tab === 'outbound' && (
        <section>
          <h2>Outbound queue</h2>
          <p className="brand-sub">Held until staff send to CBS (ff_outbound OFF).</p>
          <table className="table">
            <thead>
              <tr>
                <th>Application</th>
                <th>Tier</th>
                <th>Updated</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {outbound.map((row) => (
                <tr key={row.application_id}>
                  <td>
                    <code>{row.application_id.slice(0, 8)}</code>
                    <div>{row.user_ref}</div>
                  </td>
                  <td>{row.tier}</td>
                  <td>{new Date(row.updated_at).toLocaleString()}</td>
                  <td>
                    <button
                      className="btn"
                      type="button"
                      disabled={busy}
                      onClick={async () => {
                        setBusy(true)
                        setError(null)
                        try {
                          await portalApi.sendOutbound(row.application_id)
                          setNotice('Sent to CBS')
                          setOutbound(await portalApi.outbound())
                        } catch (e) {
                          setError(e instanceof Error ? e.message : String(e))
                        } finally {
                          setBusy(false)
                        }
                      }}
                    >
                      Send to CBS
                    </button>
                  </td>
                </tr>
              ))}
              {outbound.length === 0 && (
                <tr>
                  <td colSpan={4}>Queue empty</td>
                </tr>
              )}
            </tbody>
          </table>
        </section>
      )}

      {tab === 'inbound' && (
        <section>
          <h2>Inbound queue</h2>
          <p className="brand-sub">CBS results awaiting release to the customer app.</p>
          <table className="table">
            <thead>
              <tr>
                <th>Application</th>
                <th>Account</th>
                <th>Updated</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {inbound.map((row) => (
                <tr key={row.application_id}>
                  <td>
                    <code>{row.application_id.slice(0, 8)}</code>
                  </td>
                  <td>{row.account_number || '—'}</td>
                  <td>{new Date(row.updated_at).toLocaleString()}</td>
                  <td style={{ display: 'flex', gap: '0.4rem' }}>
                    <button
                      className="btn"
                      type="button"
                      disabled={busy}
                      onClick={async () => {
                        setBusy(true)
                        try {
                          await portalApi.releaseInbound(row.application_id, {
                            status: 'ACCOUNT_OPENED',
                            account_number: row.account_number || undefined,
                            bank_reference: row.bank_reference || undefined,
                          })
                          setNotice('Released to customer')
                          setInbound(await portalApi.inbound())
                        } catch (e) {
                          setError(e instanceof Error ? e.message : String(e))
                        } finally {
                          setBusy(false)
                        }
                      }}
                    >
                      Release open
                    </button>
                    <button
                      className="btn danger"
                      type="button"
                      disabled={busy}
                      onClick={async () => {
                        setBusy(true)
                        try {
                          await portalApi.releaseInbound(row.application_id, {
                            status: 'BANK_REJECTED',
                            reject_reason: 'Rejected by bank reviewer',
                          })
                          setNotice('Rejected and released')
                          setInbound(await portalApi.inbound())
                        } catch (e) {
                          setError(e instanceof Error ? e.message : String(e))
                        } finally {
                          setBusy(false)
                        }
                      }}
                    >
                      Reject
                    </button>
                  </td>
                </tr>
              ))}
              {inbound.length === 0 && (
                <tr>
                  <td colSpan={4}>Queue empty</td>
                </tr>
              )}
            </tbody>
          </table>
        </section>
      )}

      {tab === 'settings' && (
        <section className="stack">
          <h2>Fast Forward</h2>
          <p className="brand-sub">
            Dual independent gates. Employees can view; only Admin / Super Admin can change.
          </p>
          <div className="toggle-row">
            <div>
              <strong>Outbound (App → CBS)</strong>
              <div className="brand-sub">When OFF, submissions wait in outbound queue.</div>
            </div>
            <label>
              <input
                type="checkbox"
                checked={ffOut}
                disabled={!canManageSettings || busy}
                onChange={(e) => setFfOut(e.target.checked)}
              />{' '}
              {ffOut ? 'ON' : 'OFF'}
            </label>
          </div>
          <div className="toggle-row">
            <div>
              <strong>Inbound (CBS → App)</strong>
              <div className="brand-sub">When OFF, CBS results wait for staff release.</div>
            </div>
            <label>
              <input
                type="checkbox"
                checked={ffIn}
                disabled={!canManageSettings || busy}
                onChange={(e) => setFfIn(e.target.checked)}
              />{' '}
              {ffIn ? 'ON' : 'OFF'}
            </label>
          </div>
          {canManageSettings && (
            <button
              className="btn"
              type="button"
              disabled={busy}
              onClick={async () => {
                setBusy(true)
                setError(null)
                try {
                  const s = await portalApi.patchSettings({
                    ff_outbound: ffOut,
                    ff_inbound: ffIn,
                  })
                  setFfOut(s.ff_outbound)
                  setFfIn(s.ff_inbound)
                  setNotice('Settings saved')
                } catch (e) {
                  setError(e instanceof Error ? e.message : String(e))
                } finally {
                  setBusy(false)
                }
              }}
            >
              Save settings
            </button>
          )}
        </section>
      )}

      {tab === 'staff' && canManageStaff && (
        <section>
          <h2>Staff</h2>
          <form
            className="stack"
            style={{ marginBottom: '1.5rem' }}
            onSubmit={async (e) => {
              e.preventDefault()
              setBusy(true)
              try {
                await portalApi.inviteStaff({
                  email: inviteEmail,
                  password: invitePassword,
                  role: inviteRole,
                })
                setInviteEmail('')
                setNotice('Staff invited')
                setStaff(await portalApi.staff())
              } catch (err) {
                setError(err instanceof Error ? err.message : String(err))
              } finally {
                setBusy(false)
              }
            }}
          >
            <input
              placeholder="email"
              value={inviteEmail}
              onChange={(e) => setInviteEmail(e.target.value)}
              required
            />
            <input
              placeholder="temporary password"
              value={invitePassword}
              onChange={(e) => setInvitePassword(e.target.value)}
              required
            />
            <select value={inviteRole} onChange={(e) => setInviteRole(e.target.value)}>
              <option value="EMPLOYEE">EMPLOYEE</option>
              <option value="ADMIN">ADMIN</option>
              {meta.role === 'SUPER_ADMIN' && <option value="SUPER_ADMIN">SUPER_ADMIN</option>}
            </select>
            <button className="btn" type="submit" disabled={busy}>
              Invite
            </button>
          </form>
          <table className="table">
            <thead>
              <tr>
                <th>Email</th>
                <th>Role</th>
                <th>Active</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {staff.map((s) => (
                <tr key={s.id}>
                  <td>{s.email}</td>
                  <td>{s.role}</td>
                  <td>{s.active ? 'yes' : 'no'}</td>
                  <td>
                    {s.active && (
                      <button
                        className="btn secondary"
                        type="button"
                        onClick={async () => {
                          setBusy(true)
                          try {
                            await portalApi.revokeStaff(s.id)
                            setStaff(await portalApi.staff())
                          } catch (e) {
                            setError(e instanceof Error ? e.message : String(e))
                          } finally {
                            setBusy(false)
                          }
                        }}
                      >
                        Revoke
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {tab === 'audit' && canManageStaff && (
        <section>
          <h2>Audit</h2>
          <table className="table">
            <thead>
              <tr>
                <th>When</th>
                <th>Actor</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {audit.map((a) => (
                <tr key={a.id}>
                  <td>{new Date(a.timestamp).toLocaleString()}</td>
                  <td>
                    {a.actor_type}:{a.actor_id}
                  </td>
                  <td>{a.action}</td>
                </tr>
              ))}
              {audit.length === 0 && (
                <tr>
                  <td colSpan={3}>No bank-scoped audit events yet</td>
                </tr>
              )}
            </tbody>
          </table>
        </section>
      )}
    </div>
  )
}
