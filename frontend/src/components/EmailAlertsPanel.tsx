// Port of web/static/js/notifications.js - the "Email Alerts" slide-over,
// opened from the topbar's mail icon. Lets a logged-in user save/remove
// their OWN SMTP account so checkpoint emails go out through it (see
// core/observer_decorator/email_alerts_listener.py).

import { useEffect, useState, type FormEvent } from 'react'
import { deleteEmailConfig, getEmailConfig, setEmailConfig } from '../api/notificationsApi'

interface EmailAlertsPanelProps {
  open: boolean
  onClose: () => void
}

export function EmailAlertsPanel({ open, onClose }: EmailAlertsPanelProps) {
  const [host, setHost] = useState('')
  const [port, setPort] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [configured, setConfigured] = useState(false)
  const [saving, setSaving] = useState(false)
  const [removing, setRemoving] = useState(false)

  function resetForm() {
    setHost('')
    setPort('')
    setUsername('')
    setPassword('')
    setError('')
  }

  // openPanel() (notifications.js) loads status the instant the panel
  // opens - do the same every time `open` flips true.
  useEffect(() => {
    if (!open) return
    resetForm()
    getEmailConfig()
      .then((status) => setConfigured(status.configured))
      .catch(() => setConfigured(false))
    // resetForm() intentionally excluded - it's stable in behavior and
    // including it would just re-declare the effect's own dependency noise.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError('')

    const smtpHost = host.trim()
    const smtpPort = Number(port)
    const smtpUsername = username.trim()
    if (!smtpHost || !smtpPort || !smtpUsername || !password) return

    setSaving(true)
    try {
      await setEmailConfig({ smtp_host: smtpHost, smtp_port: smtpPort, smtp_username: smtpUsername, smtp_password: password })
      resetForm()
      setConfigured(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't save your email settings — try again.")
    } finally {
      setSaving(false)
    }
  }

  async function handleRemove() {
    setError('')
    setRemoving(true)
    try {
      await deleteEmailConfig()
      setConfigured(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't remove your email settings — try again.")
    } finally {
      setRemoving(false)
    }
  }

  return (
    <>
      <div className="trips-panel-backdrop" hidden={!open} onClick={onClose} />
      <aside className="trips-panel" hidden={!open} role="dialog" aria-modal="true" aria-label="Email checkpoint alerts">
        <div className="trips-panel-header">
          <h2>Email Alerts</h2>
          <button type="button" className="trips-panel-close" aria-label="Close email alerts panel" onClick={onClose}>
            <svg className="icon" viewBox="0 0 24 24" fill="none">
              <path d="M6 6l12 12M18 6 6 18" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
            </svg>
          </button>
        </div>

        <div className="trips-panel-body">
          <p className="email-config-hint">
            Get an email at your own address every time you reach a checkpoint. WorldWalker sends it through <strong>your own</strong> email
            account - we never see or store your password anywhere but encrypted, and we never use it for anything else.
          </p>

          <form onSubmit={handleSubmit} noValidate>
            <div className="field">
              <label className="field-label" htmlFor="email-config-host">
                SMTP host
              </label>
              <div className="field-input">
                <input id="email-config-host" type="text" placeholder="smtp.gmail.com" autoComplete="off" required value={host} onChange={(e) => setHost(e.target.value)} />
              </div>
            </div>

            <div className="field">
              <label className="field-label" htmlFor="email-config-port">
                SMTP port
              </label>
              <div className="field-input">
                <input id="email-config-port" type="number" placeholder="587" autoComplete="off" required value={port} onChange={(e) => setPort(e.target.value)} />
              </div>
            </div>

            <div className="field">
              <label className="field-label" htmlFor="email-config-username">
                Email address
              </label>
              <div className="field-input">
                <input
                  id="email-config-username"
                  type="email"
                  placeholder="you@example.com"
                  autoComplete="off"
                  required
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                />
              </div>
            </div>

            <div className="field">
              <label className="field-label" htmlFor="email-config-password">
                Password (or app password)
              </label>
              <div className="field-input">
                <input
                  id="email-config-password"
                  type="password"
                  placeholder="••••••••"
                  autoComplete="off"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </div>
            </div>

            {error && <p className="auth-error">{error}</p>}
            {configured && !error && <p className="email-config-status">Email alerts are on for your account.</p>}

            <div className="email-config-actions">
              <button type="submit" className="btn btn-start" disabled={saving}>
                Save
              </button>
              {configured && (
                <button type="button" className="trips-bulk-btn trips-bulk-btn-danger" disabled={removing} onClick={handleRemove}>
                  Remove
                </button>
              )}
            </div>
          </form>
        </div>
      </aside>
    </>
  )
}
