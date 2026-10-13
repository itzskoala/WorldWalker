// Identity block at the top of the Profile screen: cover photo, avatar
// (the one piece of this screen that's actually wired up - see
// handlePhotoChange below), display name, and a meta row of member-since
// + lifetime steps. Lives inside ProfilePage's normal screen-inner-wide
// column (not a full-bleed hero) so the cover reads as a rounded card
// like the rest of the page, not an edge-to-edge banner.

import { useRef, useState, type ChangeEvent, type KeyboardEvent } from 'react'
import { useAuth } from '../../auth/AuthContext'
import { IconCalendar, IconCamera, IconPencil, IconShoe } from '../icons'
import { photoUrl } from '../../mock/profileMock'

function formatMemberSince(date: Date): string {
  return `Member since ${date.toLocaleDateString(undefined, { month: 'long', year: 'numeric' })}`
}

interface ProfileHeroProps {
  lifetimeSteps: number
}

export function ProfileHero({ lifetimeSteps }: ProfileHeroProps) {
  const { user } = useAuth()
  const fileInputRef = useRef<HTMLInputElement>(null)
  // Local-only override of the avatar - picking a photo here previews it
  // instantly but isn't persisted anywhere (no account field for it
  // yet), so it resets on reload. That matches this pass's scope: design
  // the "set/change photo" interaction, not store the result.
  const [avatarOverride, setAvatarOverride] = useState<string | null>(null)

  // No display-name field on the account (accounts/schemas.py's UserOut
  // is just id/email/is_active/created_at) - the part before "@" is the
  // only thing worth showing until there's a real one to store.
  const fallbackName = user?.email?.split('@')[0] || 'Traveler'
  // Same scope as the avatar override above - "Edit Profile" only edits
  // this component's local copy of the name, not the account itself.
  const [nameOverride, setNameOverride] = useState<string | null>(null)
  const [isEditingName, setIsEditingName] = useState(false)
  const [nameDraft, setNameDraft] = useState('')
  const displayName = nameOverride || fallbackName
  const avatarSrc = avatarOverride

  function handlePhotoChange(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setAvatarOverride(URL.createObjectURL(file))
  }

  function startEditingName() {
    setNameDraft(displayName)
    setIsEditingName(true)
  }

  function saveName() {
    const trimmed = nameDraft.trim()
    if (trimmed) setNameOverride(trimmed)
    setIsEditingName(false)
  }

  function handleNameKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter') saveName()
    if (e.key === 'Escape') setIsEditingName(false)
  }

  return (
    <section className="profile-hero" aria-label="Profile identity">
      <div className="profile-cover" style={{ backgroundImage: `url(${photoUrl('worldwalker-cover', 1200, 420)})` }} />

      <div className="profile-hero-body">
        <div className="profile-avatar-wrap">
          {avatarSrc ? (
            <img className="profile-avatar-photo" src={avatarSrc} alt="" />
          ) : (
            <span className="profile-avatar-fallback" aria-hidden="true">
              {displayName.charAt(0).toUpperCase()}
            </span>
          )}
          <button type="button" className="profile-avatar-edit" aria-label="Change profile photo" onClick={() => fileInputRef.current?.click()}>
            <IconCamera className="icon icon-sm" />
          </button>
          <input ref={fileInputRef} type="file" accept="image/*" hidden onChange={handlePhotoChange} />
        </div>

        <div className="profile-identity">
          {isEditingName ? (
            <input
              className="profile-name-input"
              value={nameDraft}
              autoFocus
              onChange={(e) => setNameDraft(e.target.value)}
              onBlur={saveName}
              onKeyDown={handleNameKeyDown}
            />
          ) : (
            <h1 className="profile-name">{displayName}</h1>
          )}
          <p className="profile-tagline">Every mile tells a story.</p>
          <div className="profile-meta-row">
            <span className="profile-meta-item">
              <IconCalendar className="icon icon-sm" />
              {user?.created_at ? formatMemberSince(new Date(user.created_at)) : 'Member since —'}
            </span>
            <span className="profile-meta-divider" aria-hidden="true" />
            <span className="profile-meta-item">
              <IconShoe className="icon icon-sm" />
              {lifetimeSteps.toLocaleString()} lifetime steps
            </span>
          </div>
        </div>

        <button type="button" className="profile-edit-btn" onClick={startEditingName}>
          <IconPencil className="icon icon-sm" />
          Edit Profile
        </button>
      </div>
    </section>
  )
}
