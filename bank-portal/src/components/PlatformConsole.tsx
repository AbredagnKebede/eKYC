'use client'

import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import {
  clearPlatformMeta,
  loadPlatformMeta,
  platformApi,
  savePlatformMeta,
} from '@/lib/api'
import type { PartnerBankRow } from '@/lib/api'

type IssuedCreds = {
  bank_id: string
  super_admin_email: string
  temporary_password: string
}

export default function PlatformConsole() {
  const [meta, setMeta] = useState<ReturnType<typeof loadPlatformMeta>>(null)
  const [hydrated, setHydrated] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')

  const [banks, setBanks] = useState<PartnerBankRow[]>([])
  const [issued, setIssued] = useState<IssuedCreds | null>(null)

  const [newId, setNewId] = useState('bank_')
  const [newName, setNewName] = useState('')
  const [newCode, setNewCode] = useState('')
  const [newCity, setNewCity] = useState('Addis Ababa')
  const [newAdminEmail, setNewAdminEmail] = useState('')

  useEffect(() => {
    setMeta(loadPlatformMeta())
    setHydrated(true)
  }, [])

  async function refreshBanks() {
    if (!loadPlatformMeta()) return
    setBanks(await platformApi.banks())
  }

  useEffect(() => {
    if (!hydrated || !meta) return
    void (async () => {
      try {
        setError(null)
        await refreshBanks()
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e))
      }
    })()
  }, [hydrated, meta])

  async function onLogin(e: FormEvent) {
    e.preventDefault()
    if (!email.trim() || !password) {
      setError('Enter operator email and password.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      const res = await platformApi.login(email.trim(), password)
      const next = { token: res.token, email: res.email, role: res.role }
      savePlatformMeta(next)
      setMeta(next)
      setPassword('')
      setNotice('Signed in as platform operator.')
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  function onLogout() {
    clearPlatformMeta()
    setMeta(null)
    setBanks([])
    setIssued(null)
    setNotice(null)
  }

  async function onCreateBank(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      const res = await platformApi.createBank({
        bank_id: newId.trim().toLowerCase(),
        bank_name: newName.trim(),
        short_code: newCode.trim().toUpperCase(),
        hq_city: newCity.trim() || 'Addis Ababa',
        supported_tiers: ['standard', 'diaspora'],
        super_admin_email: newAdminEmail.trim() || undefined,
      })
      setIssued({
        bank_id: res.bank.bank_id,
        super_admin_email: res.super_admin_email,
        temporary_password: res.temporary_password,
      })
      setNotice(`Onboarded ${res.bank.bank_name}. Copy the temporary password now — it is shown once.`)
      setNewId('bank_')
      setNewName('')
      setNewCode('')
      setNewAdminEmail('')
      await refreshBanks()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  async function toggleActive(row: PartnerBankRow) {
    setBusy(true)
    setError(null)
    try {
      await platformApi.patchBank(row.bank_id, { active: !row.active })
      setNotice(`${row.bank_name} is now ${row.active ? 'inactive' : 'active'}.`)
      await refreshBanks()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  async function resetSuper(row: PartnerBankRow) {
    if (!window.confirm(`Rotate Super Admin password for ${row.bank_name}?`)) return
    setBusy(true)
    setError(null)
    try {
      const res = await platformApi.resetSuperAdmin(row.bank_id)
      setIssued({
        bank_id: res.bank_id,
        super_admin_email: res.super_admin_email,
        temporary_password: res.temporary_password,
      })
      setNotice('Super Admin password rotated. Copy it now.')
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  async function copyText(text: string) {
    try {
      await navigator.clipboard.writeText(text)
      setNotice('Copied to clipboard.')
    } catch {
      setError('Clipboard unavailable — select and copy manually.')
    }
  }

  if (!hydrated) {
    return <div className="shell loading-shell">Loading…</div>
  }

  if (!meta) {
    return (
      <div className="shell login-shell platform-shell">
        <div className="login-layout">
          <div className="login-brand">
            <div className="eyebrow">Fayda Onboard</div>
            <h1>Platform console</h1>
            <p>
              Onboard partner banks, issue Super Admin credentials, and control which banks appear
              in mobile and the staff portal.
            </p>
          </div>
          <form className="login-panel" onSubmit={onLogin} autoComplete="on">
            <h2>Operator sign in</h2>
            <p className="hint">Platform credentials — not bank staff tokens.</p>
            <div className="field">
              <label htmlFor="op-email">Email</label>
              <input
                id="op-email"
                type="email"
                autoComplete="username"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>
            <div className="field">
              <label htmlFor="op-password">Password</label>
              <input
                id="op-password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>
            {error ? <p className="banner error">{error}</p> : null}
            <button type="submit" className="btn primary" disabled={busy}>
              {busy ? 'Signing in…' : 'Sign in'}
            </button>
            <p className="hint">
              Bank staff? Use the <a href="/">bank portal</a> instead.
            </p>
          </form>
        </div>
      </div>
    )
  }

  return (
    <div className="shell platform-shell">
      <header className="topbar">
        <div>
          <div className="eyebrow">Platform</div>
          <h1>Partner banks</h1>
        </div>
        <div className="topbar-actions">
          <span className="pill muted">{meta.email}</span>
          <button type="button" className="btn ghost" onClick={onLogout}>
            Sign out
          </button>
        </div>
      </header>

      {error ? <p className="banner error">{error}</p> : null}
      {notice ? <p className="banner ok">{notice}</p> : null}

      {issued ? (
        <section className="panel issued-creds">
          <h2>One-time credentials</h2>
          <p className="hint">
            Share with the bank contact, then clear this panel. The password is not stored in
            plaintext.
          </p>
          <dl className="cred-grid">
            <div>
              <dt>Bank</dt>
              <dd>{issued.bank_id}</dd>
            </div>
            <div>
              <dt>Super Admin email</dt>
              <dd>
                {issued.super_admin_email}{' '}
                <button type="button" className="btn ghost compact" onClick={() => void copyText(issued.super_admin_email)}>
                  Copy
                </button>
              </dd>
            </div>
            <div>
              <dt>Temporary password</dt>
              <dd>
                <code>{issued.temporary_password}</code>{' '}
                <button
                  type="button"
                  className="btn ghost compact"
                  onClick={() => void copyText(issued.temporary_password)}
                >
                  Copy
                </button>
              </dd>
            </div>
          </dl>
          <button type="button" className="btn ghost" onClick={() => setIssued(null)}>
            Clear from screen
          </button>
        </section>
      ) : null}

      <section className="panel">
        <h2>Add bank</h2>
        <form className="stack-form" onSubmit={onCreateBank}>
          <div className="field-row">
            <div className="field">
              <label htmlFor="new-id">Bank ID</label>
              <input
                id="new-id"
                value={newId}
                onChange={(e) => setNewId(e.target.value)}
                placeholder="bank_example"
                required
              />
            </div>
            <div className="field">
              <label htmlFor="new-code">Short code</label>
              <input
                id="new-code"
                value={newCode}
                onChange={(e) => setNewCode(e.target.value)}
                placeholder="EX"
                required
              />
            </div>
          </div>
          <div className="field">
            <label htmlFor="new-name">Display name</label>
            <input
              id="new-name"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="Example Bank"
              required
            />
          </div>
          <div className="field-row">
            <div className="field">
              <label htmlFor="new-city">HQ city</label>
              <input id="new-city" value={newCity} onChange={(e) => setNewCity(e.target.value)} />
            </div>
            <div className="field">
              <label htmlFor="new-admin">Super Admin email (optional)</label>
              <input
                id="new-admin"
                type="email"
                value={newAdminEmail}
                onChange={(e) => setNewAdminEmail(e.target.value)}
                placeholder="admin@example.et"
              />
            </div>
          </div>
          <button type="submit" className="btn primary" disabled={busy}>
            {busy ? 'Creating…' : 'Create bank + issue credentials'}
          </button>
        </form>
      </section>

      <section className="panel">
        <h2>Catalogue ({banks.length})</h2>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Bank</th>
                <th>Code</th>
                <th>Status</th>
                <th>Tiers</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {banks.map((row) => (
                <tr key={row.bank_id}>
                  <td>
                    <strong>{row.bank_name}</strong>
                    <div className="muted small">{row.bank_id}</div>
                  </td>
                  <td>{row.short_code}</td>
                  <td>
                    <span className={`pill ${row.active ? 'ok' : 'muted'}`}>
                      {row.active ? 'Active' : 'Inactive'}
                    </span>
                  </td>
                  <td>{row.supported_tiers.join(', ')}</td>
                  <td className="actions">
                    <button
                      type="button"
                      className="btn ghost compact"
                      disabled={busy}
                      onClick={() => void toggleActive(row)}
                    >
                      {row.active ? 'Deactivate' : 'Activate'}
                    </button>
                    <button
                      type="button"
                      className="btn ghost compact"
                      disabled={busy}
                      onClick={() => void resetSuper(row)}
                    >
                      Reset Super Admin
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}
