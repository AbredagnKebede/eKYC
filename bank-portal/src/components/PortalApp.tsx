'use client'

import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import {
  clearMeta,
  fetchPublicBanks,
  loadMeta,
  portalApi,
  saveMeta,
} from '@/lib/api'
import type { AuditItem, PublicBank, QueueItem, StaffItem } from '@/lib/api'

type Tab = 'dashboard' | 'outbound' | 'inbound' | 'settings' | 'staff' | 'audit'

function bankLabel(id: string, banks: PublicBank[]) {
  return banks.find((b) => b.bank_id === id)?.bank_name ?? id
}

function shortId(id: string) {
  return id.replace(/-/g, '').slice(0, 8)
}

function roleLabel(role: string) {
  return role.replace(/_/g, ' ').toLowerCase().replace(/^\w/, (c) => c.toUpperCase())
}

export default function PortalApp() {
  const [meta, setMeta] = useState<ReturnType<typeof loadMeta>>(null)
  const [hydrated, setHydrated] = useState(false)
  const [tab, setTab] = useState<Tab>('dashboard')
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [bankId, setBankId] = useState('')
  const [banks, setBanks] = useState<PublicBank[]>([])
  const [banksLoading, setBanksLoading] = useState(true)

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
  const [invitePassword, setInvitePassword] = useState('')
  const [inviteRole, setInviteRole] = useState('EMPLOYEE')

  useEffect(() => {
    setMeta(loadMeta())
    setHydrated(true)
    void (async () => {
      setBanksLoading(true)
      try {
        const list = await fetchPublicBanks()
        setBanks(list)
        if (list.length && !bankId) setBankId(list[0].bank_id)
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Could not load partner banks.')
      } finally {
        setBanksLoading(false)
      }
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
    if (!bankId || !email.trim() || !password) {
      setError('Choose your bank and enter email and password.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      const res = await portalApi.login(email.trim(), password, bankId)
      const next = {
        token: res.token,
        bank_id: res.bank_id,
        role: res.role,
        email: res.email,
      }
      saveMeta(next)
      setMeta(next)
      setPassword('')
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
    setPassword('')
    setNotice(null)
    setError(null)
  }

  function go(next: Tab) {
    setNotice(null)
    setError(null)
    setTab(next)
  }

  if (!hydrated) {
    return (
      <div className="app-shell">
        <div className="loading-shell">Loading portal…</div>
      </div>
    )
  }

  if (!meta) {
    return (
      <div className="app-shell">
        <div className="login-layout">
          <div className="login-brand">
            <div className="eyebrow">Fayda Onboard</div>
            <h1>Bank Portal</h1>
            <p>
              Review outbound and inbound applications, control Fast Forward, and manage staff —
              scoped to your bank only.
            </p>
          </div>

          <form className="login-panel" onSubmit={onLogin} autoComplete="on">
            <h2>Staff sign in</h2>
            <p className="hint">Use the credentials issued by your bank administrator.</p>

            <div className="field">
              <label htmlFor="bank">Bank</label>
              <select
                id="bank"
                value={bankId}
                onChange={(e) => setBankId(e.target.value)}
                required
                autoComplete="organization"
                disabled={banksLoading || banks.length === 0}
              >
                <option value="" disabled>
                  {banksLoading ? 'Loading banks…' : 'Select your bank'}
                </option>
                {banks.map((b) => (
                  <option key={b.bank_id} value={b.bank_id}>
                    {b.bank_name}
                  </option>
                ))}
              </select>
            </div>

            <div className="field">
              <label htmlFor="email">Work email</label>
              <input
                id="email"
                type="email"
                autoComplete="username"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@bank.et"
                required
              />
            </div>

            <div className="field">
              <label htmlFor="password">Password</label>
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                required
                minLength={8}
              />
            </div>

            {error && <p className="err">{error}</p>}

            <button className="btn primary-accent btn-block" type="submit" disabled={busy}>
              {busy ? 'Signing in…' : 'Sign in'}
            </button>
          </form>
        </div>
      </div>
    )
  }

  const tabs: [Tab, string][] = [
    ['dashboard', 'Home'],
    ['outbound', 'Outbound'],
    ['inbound', 'Inbound'],
    ['settings', 'Settings'],
    ...(canManageStaff
      ? ([
          ['staff', 'Staff'],
          ['audit', 'Audit'],
        ] as [Tab, string][])
      : []),
  ]

  return (
    <div className="app-shell">
      <header className="topbar">
        <div>
          <h1 className="brand-mark">Fayda Bank Portal</h1>
          <div className="topbar-meta">
            <span className="pill muted">{bankLabel(meta.bank_id, banks)}</span>
            <span className="pill">{roleLabel(meta.role)}</span>
          </div>
        </div>
        <button className="btn secondary" type="button" onClick={logout}>
          Sign out
        </button>
      </header>

      <nav className="nav" aria-label="Portal sections">
        {tabs.map(([id, label]) => (
          <button
            key={id}
            type="button"
            className={tab === id ? 'active' : ''}
            onClick={() => go(id)}
          >
            {label}
          </button>
        ))}
      </nav>

      {error && <p className="err">{error}</p>}
      {notice && <p className="ok">{notice}</p>}

      {tab === 'dashboard' && (
        <section>
          <div className="section-head">
            <h2>Overview</h2>
            <p>Queue depth and Fast Forward status for {bankLabel(meta.bank_id, banks)}.</p>
          </div>

          {dash ? (
            <>
              <div className="metrics">
                <div className="metric">
                  <div className="label">Waiting to send</div>
                  <div className="n">{dash.outbound_count}</div>
                </div>
                <div className="metric">
                  <div className="label">Waiting to release</div>
                  <div className="n">{dash.inbound_count}</div>
                </div>
                <div className="metric">
                  <div className="label">App → CBS</div>
                  <div className={`n ${dash.ff_outbound ? 'on' : 'off'}`}>
                    {dash.ff_outbound ? 'Auto' : 'Manual'}
                  </div>
                </div>
                <div className="metric">
                  <div className="label">CBS → App</div>
                  <div className={`n ${dash.ff_inbound ? 'on' : 'off'}`}>
                    {dash.ff_inbound ? 'Auto' : 'Manual'}
                  </div>
                </div>
              </div>

              <div className="quick-actions">
                <button type="button" className="quick-action" onClick={() => go('outbound')}>
                  <strong>Outbound queue</strong>
                  <span>
                    {dash.outbound_count === 0
                      ? 'Nothing waiting to send to CBS'
                      : `${dash.outbound_count} application${dash.outbound_count === 1 ? '' : 's'} ready to send`}
                  </span>
                </button>
                <button type="button" className="quick-action" onClick={() => go('inbound')}>
                  <strong>Inbound queue</strong>
                  <span>
                    {dash.inbound_count === 0
                      ? 'Nothing waiting for customer release'
                      : `${dash.inbound_count} result${dash.inbound_count === 1 ? '' : 's'} to confirm`}
                  </span>
                </button>
              </div>
            </>
          ) : (
            <p className="empty">Loading overview…</p>
          )}
        </section>
      )}

      {tab === 'outbound' && (
        <section>
          <div className="section-head">
            <h2>Outbound</h2>
            <p>Applications held until staff send them to the bank CBS.</p>
          </div>

          <div className="queue-cards">
            {outbound.length === 0 && <p className="empty">Queue is empty.</p>}
            {outbound.map((row) => (
              <article key={row.application_id} className="queue-card">
                <div className="row">
                  <span className="k">Application</span>
                  <code>{shortId(row.application_id)}</code>
                </div>
                <div className="row">
                  <span className="k">Tier</span>
                  <span>{row.tier}</span>
                </div>
                <div className="row">
                  <span className="k">Updated</span>
                  <span>{new Date(row.updated_at).toLocaleString()}</span>
                </div>
                <div className="actions">
                  <button
                    className="btn primary-accent"
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
                </div>
              </article>
            ))}
          </div>

          <div className="desktop-table table-wrap">
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
                      <code>{shortId(row.application_id)}</code>
                    </td>
                    <td>{row.tier}</td>
                    <td>{new Date(row.updated_at).toLocaleString()}</td>
                    <td>
                      <button
                        className="btn primary-accent"
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
                    <td colSpan={4} className="empty">
                      Queue is empty.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {tab === 'inbound' && (
        <section>
          <div className="section-head">
            <h2>Inbound</h2>
            <p>CBS results waiting for your confirmation before the customer sees them.</p>
          </div>

          <div className="queue-cards">
            {inbound.length === 0 && <p className="empty">Queue is empty.</p>}
            {inbound.map((row) => (
              <article key={row.application_id} className="queue-card">
                <div className="row">
                  <span className="k">Application</span>
                  <code>{shortId(row.application_id)}</code>
                </div>
                <div className="row">
                  <span className="k">Account</span>
                  <span>{row.account_number || '—'}</span>
                </div>
                <div className="row">
                  <span className="k">Updated</span>
                  <span>{new Date(row.updated_at).toLocaleString()}</span>
                </div>
                <div className="actions">
                  <button
                    className="btn primary-accent"
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
                </div>
              </article>
            ))}
          </div>

          <div className="desktop-table table-wrap">
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
                      <code>{shortId(row.application_id)}</code>
                    </td>
                    <td>{row.account_number || '—'}</td>
                    <td>{new Date(row.updated_at).toLocaleString()}</td>
                    <td>
                      <div className="btn-row">
                        <button
                          className="btn primary-accent"
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
                      </div>
                    </td>
                  </tr>
                ))}
                {inbound.length === 0 && (
                  <tr>
                    <td colSpan={4} className="empty">
                      Queue is empty.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {tab === 'settings' && (
        <section className="stack">
          <div className="section-head">
            <h2>Fast Forward</h2>
            <p>When automatic routing is off, items wait in the matching queue for staff action.</p>
          </div>

          <div className="toggle-row">
            <div>
              <strong>Outbound — App → CBS</strong>
              <div className="desc">Auto-send submissions, or hold them in Outbound.</div>
            </div>
            <label className="switch">
              <input
                type="checkbox"
                checked={ffOut}
                disabled={!canManageSettings || busy}
                onChange={(e) => setFfOut(e.target.checked)}
              />
              {ffOut ? 'Auto' : 'Manual'}
            </label>
          </div>

          <div className="toggle-row">
            <div>
              <strong>Inbound — CBS → App</strong>
              <div className="desc">Auto-release results, or hold them in Inbound.</div>
            </div>
            <label className="switch">
              <input
                type="checkbox"
                checked={ffIn}
                disabled={!canManageSettings || busy}
                onChange={(e) => setFfIn(e.target.checked)}
              />
              {ffIn ? 'Auto' : 'Manual'}
            </label>
          </div>

          {canManageSettings ? (
            <button
              className="btn primary-accent"
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
          ) : (
            <p className="hint">Only admins can change Fast Forward.</p>
          )}
        </section>
      )}

      {tab === 'staff' && canManageStaff && (
        <section>
          <div className="section-head">
            <h2>Staff</h2>
            <p>Invite colleagues for this bank. Roles control who can change settings.</p>
          </div>

          <form
            className="invite-box stack"
            onSubmit={async (e) => {
              e.preventDefault()
              setBusy(true)
              try {
                await portalApi.inviteStaff({
                  email: inviteEmail.trim(),
                  password: invitePassword,
                  role: inviteRole,
                })
                setInviteEmail('')
                setInvitePassword('')
                setNotice('Invitation created')
                setStaff(await portalApi.staff())
              } catch (err) {
                setError(err instanceof Error ? err.message : String(err))
              } finally {
                setBusy(false)
              }
            }}
          >
            <div className="field">
              <label htmlFor="invite-email">Email</label>
              <input
                id="invite-email"
                type="email"
                value={inviteEmail}
                onChange={(e) => setInviteEmail(e.target.value)}
                placeholder="colleague@bank.et"
                required
              />
            </div>
            <div className="field">
              <label htmlFor="invite-password">Temporary password</label>
              <input
                id="invite-password"
                type="password"
                value={invitePassword}
                onChange={(e) => setInvitePassword(e.target.value)}
                placeholder="At least 8 characters"
                required
                minLength={8}
              />
            </div>
            <div className="field">
              <label htmlFor="invite-role">Role</label>
              <select
                id="invite-role"
                value={inviteRole}
                onChange={(e) => setInviteRole(e.target.value)}
              >
                <option value="EMPLOYEE">Employee</option>
                <option value="ADMIN">Admin</option>
                {meta.role === 'SUPER_ADMIN' && <option value="SUPER_ADMIN">Super admin</option>}
              </select>
            </div>
            <button className="btn primary-accent" type="submit" disabled={busy}>
              Invite staff
            </button>
          </form>

          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Email</th>
                  <th>Role</th>
                  <th>Status</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {staff.map((s) => (
                  <tr key={s.id}>
                    <td>{s.email}</td>
                    <td>{roleLabel(s.role)}</td>
                    <td>{s.active ? 'Active' : 'Revoked'}</td>
                    <td>
                      {s.active && (
                        <button
                          className="btn ghost"
                          type="button"
                          onClick={async () => {
                            setBusy(true)
                            try {
                              await portalApi.revokeStaff(s.id)
                              setStaff(await portalApi.staff())
                              setNotice('Access revoked')
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
          </div>
        </section>
      )}

      {tab === 'audit' && canManageStaff && (
        <section>
          <div className="section-head">
            <h2>Audit</h2>
            <p>Recent bank-scoped actions for this institution.</p>
          </div>
          <div className="table-wrap">
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
                      {a.actor_type} · {a.actor_id}
                    </td>
                    <td>{a.action}</td>
                  </tr>
                ))}
                {audit.length === 0 && (
                  <tr>
                    <td colSpan={3} className="empty">
                      No audit events yet.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  )
}
