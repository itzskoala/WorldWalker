// Email starts collapsed to plain text - "Email" label, the address
// itself, an underlined "Edit" link - instead of a bordered box. Clicking
// Edit swaps in a real (now editable) input for a *new* address plus a
// Cancel/Change row; Cancel collapses back without changing anything.
//
// There's still no backend route for changing the account email itself
// (accounts/schemas.py's ProfileUpdateRequest has no email field - that'd
// need its own verification flow) - same "design the interaction, not
// the storage" scope ProfilePage.tsx's Links field and account-deletion
// button already carry. Change does run the address through the real
// GET /auth/validate-email format check (useAuth().validateEmail), so
// the red/green feedback is honest about *that* much; a page reload will
// still show the real account email until a persistence route exists.

import { useState } from 'react'
import { useAuth } from '../../auth/AuthContext'
import { useTimedMessage } from '../../hooks/useTimedMessage'
import { ProfileInlineMessage } from './ProfileInlineMessage'

interface ProfileEmailFieldProps {
  email: string
}

export function ProfileEmailField({ email }: ProfileEmailFieldProps) {
  const { validateEmail } = useAuth()
  const [editing, setEditing] = useState(false)
  const [displayEmail, setDisplayEmail] = useState(email)
  const [draft, setDraft] = useState('')
  const [checking, setChecking] = useState(false)
  const [message, setMessage] = useTimedMessage()

  function openEdit() {
    setDraft('')
    setMessage(null)
    setEditing(true)
  }

  function cancel() {
    setEditing(false)
    setDraft('')
  }

  async function handleChange() {
    const next = draft.trim()
    if (!next || next === displayEmail) {
      setMessage({ tone: 'error', text: 'enter a new email address' })
      return
    }
    setChecking(true)
    try {
      const valid = await validateEmail(next)
      if (!valid) {
        setMessage({ tone: 'error', text: 'enter a new email address' })
        return
      }
      setDisplayEmail(next)
      setEditing(false)
      setMessage({ tone: 'success', text: 'Email updated successfully' })
    } finally {
      setChecking(false)
    }
  }

  if (!editing) {
    return (
      <div className="profile-page-field">
        <span className="profile-page-label">Email</span>
        <div className="profile-email-display">
          <span className="profile-email-value">{displayEmail}</span>
          <button type="button" className="profile-page-link-action profile-page-link-action-dark" onClick={openEdit}>
            Edit
          </button>
        </div>
        {message && <ProfileInlineMessage tone={message.tone}>{message.text}</ProfileInlineMessage>}
      </div>
    )
  }

  return (
    <div className="profile-page-field">
      <label className="profile-page-label" htmlFor="profile-email">
        Email
      </label>
      <input
        id="profile-email"
        className="profile-page-input"
        type="email"
        placeholder="Enter a new email address"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
      />
      <div className="profile-page-email-actions">
        <button type="button" className="profile-page-link-action" onClick={cancel}>
          Cancel
        </button>
        <button
          type="button"
          className="profile-page-link-action profile-page-link-action-dark"
          disabled={checking}
          onClick={handleChange}
        >
          Change
        </button>
      </div>
      {message && <ProfileInlineMessage tone={message.tone}>{message.text}</ProfileInlineMessage>}
    </div>
  )
}
