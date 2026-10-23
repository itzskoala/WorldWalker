// Profile settings screen - avatar + account form, wired to
// user_profile/profile_page.py's functions via PATCH /auth/me
// (accounts/router.py). Links/account-deletion have no backend support
// yet, so those controls render but don't persist - same "design the
// interaction, not the storage" scope ProfileHero.tsx used for its old
// avatar/name overrides. Email change has no backend route either (see
// ProfileEmailField.tsx's own note). Username is the one field with real
// server-side validation - format + uniqueness, both enforced again on
// submit by accounts/service.py's update_username() regardless of what
// ProfileUsernameField.tsx's live check already caught. Each piece of
// the form is its own component under components/profile/ - this page
// just owns the form state and wires them together.

import { useEffect, useState, type FormEvent } from 'react'
import { useAuth } from '../auth/AuthContext'
import { ProfileAvatarUpload } from '../components/profile/ProfileAvatarUpload'
import { ProfileEmailField } from '../components/profile/ProfileEmailField'
import { ProfileField } from '../components/profile/ProfileField'
import { ProfileFormActions } from '../components/profile/ProfileFormActions'
import { ProfileMetaList } from '../components/profile/ProfileMetaList'
import { ProfileUsernameField } from '../components/profile/ProfileUsernameField'
import { useTimedMessage } from '../hooks/useTimedMessage'

interface ProfilePageProps {
  active: boolean
}

export function ProfilePage({ active }: ProfilePageProps) {
  const { user, updateProfile } = useAuth()

  const [username, setUsername] = useState('')
  const [fName, setFName] = useState('')
  const [lName, setLName] = useState('')
  const [bio, setBio] = useState('')
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useTimedMessage()

  useEffect(() => {
    if (!active || !user) return
    setUsername(user.username ?? '')
    setFName(user.f_name ?? '')
    setLName(user.l_name ?? '')
    setBio(user.bio ?? '')
  }, [active, user])

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setSaving(true)
    setMessage(null)
    try {
      await updateProfile({ username, f_name: fName, l_name: lName, bio })
      setMessage({ tone: 'success', text: 'User information updated' })
    } catch (err) {
      setMessage({ tone: 'error', text: err instanceof Error ? err.message : "Couldn't update your profile." })
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="screen" id="screen-profile" aria-label="Profile">
      <div className="screen-inner screen-inner-wide profile-page">
        <h1 className="profile-page-title">Profile</h1>

        <div className="profile-page-header">
          <ProfileAvatarUpload
            photoUrl={user?.profile_photo}
            fallbackLetter={(user?.username || user?.email || '?').charAt(0).toUpperCase()}
            onUpload={(dataUrl) => updateProfile({ profile_photo: dataUrl })}
          />
          <ProfileMetaList
            lifetimeSteps={user?.lifetime_steps ?? 0}
            postcardsSum={user?.postcards_sum ?? 0}
            memberSince={user?.member_since}
          />
        </div>

        <form className="profile-page-form" onSubmit={handleSubmit}>
          <ProfileEmailField email={user?.email ?? ''} />

          <ProfileUsernameField value={username} onChange={setUsername} />

          <div className="profile-page-row">
            <ProfileField id="profile-fname" label="First name" value={fName} onChange={setFName} />
            <ProfileField id="profile-lname" label="Last name" value={lName} onChange={setLName} />
          </div>

          <ProfileField id="profile-bio" label="Bio" value={bio} onChange={setBio} />

          <div className="profile-page-field">
            <label className="profile-page-label">Links</label>
          </div>

          <ProfileFormActions saving={saving} message={message} />
        </form>
      </div>
    </section>
  )
}
