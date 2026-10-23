// Username's own live validation (ProfilePage.tsx's account form) -
// checks format instantly client-side, then debounces a real call to
// GET /auth/validate-username (accounts/router.py) for the uniqueness
// check. accounts/service.py's update_username() re-enforces both rules
// server-side on the real PATCH /auth/me submit regardless - this is
// purely a UX nicety, same "never trust the client-side pass alone"
// contract the signup form's email check already follows.

import { useEffect, useRef, useState } from 'react'
import { useAuth } from '../../auth/AuthContext'
import { ProfileInlineMessage } from './ProfileInlineMessage'

const USERNAME_FORMAT_RE = /^[A-Za-z0-9_]+$/
const CHECK_DEBOUNCE_MS = 500

interface ProfileUsernameFieldProps {
  value: string
  onChange: (value: string) => void
}

export function ProfileUsernameField({ value, onChange }: ProfileUsernameFieldProps) {
  const { validateUsername } = useAuth()
  const [error, setError] = useState<string | null>(null)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  // Guards against a slower, earlier check's response landing after a
  // faster, later one - only the most recent keystroke's result ever
  // gets to set the message.
  const requestIdRef = useRef(0)

  useEffect(
    () => () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    },
    [],
  )

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)

    if (!value || !USERNAME_FORMAT_RE.test(value)) {
      setError(value ? 'must contain only letters, numbers, and underscores' : null)
      return
    }

    setError(null)
    const requestId = ++requestIdRef.current
    debounceRef.current = setTimeout(() => {
      validateUsername(value).then((result) => {
        if (requestIdRef.current !== requestId) return
        if (!result.valid && result.reason === 'taken') {
          setError('username already in use')
        }
      })
    }, CHECK_DEBOUNCE_MS)
  }, [value, validateUsername])

  return (
    <div className="profile-page-field">
      <label className="profile-page-label" htmlFor="profile-username">
        Username
      </label>
      <input id="profile-username" className="profile-page-input" value={value} onChange={(e) => onChange(e.target.value)} />
      {error && <ProfileInlineMessage tone="error">{error}</ProfileInlineMessage>}
    </div>
  )
}
