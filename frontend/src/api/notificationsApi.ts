// Typed client for notifications/router.py's /notifications/email-config
// routes - a user's own SMTP account for checkpoint email alerts.

import type { EmailConfigRequest, EmailConfigStatus } from '../types/api'
import { apiFetch, parseErrorMessage } from './httpClient'

export async function getEmailConfig(): Promise<EmailConfigStatus> {
  const res = await apiFetch('/notifications/email-config')
  if (!res.ok) throw new Error(await parseErrorMessage(res, "Couldn't load your email alert settings."))
  return res.json() as Promise<EmailConfigStatus>
}

export async function setEmailConfig(body: EmailConfigRequest): Promise<EmailConfigStatus> {
  const res = await apiFetch('/notifications/email-config', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(await parseErrorMessage(res, 'smtp_host, smtp_port, smtp_username, and smtp_password are all required.'))
  return res.json() as Promise<EmailConfigStatus>
}

export async function deleteEmailConfig(): Promise<EmailConfigStatus> {
  const res = await apiFetch('/notifications/email-config', { method: 'DELETE' })
  if (!res.ok) throw new Error(await parseErrorMessage(res, "Couldn't remove your email alert settings."))
  return res.json() as Promise<EmailConfigStatus>
}
