// The logged-in navbar - deliberately minimal: logo, the Google Health
// connection status (existing backend - see hooks/useGoogleHealthConnection.ts,
// shared with Sidebar.tsx's own connection button, not a second
// implementation), and the profile photo. No email, no extra nav links -
// MarketingHeader.tsx is the separate, unrelated signed-out navbar; this
// one only ever renders inside AppShell, which only mounts once someone
// is actually signed in.

import { useAuth } from '../auth/AuthContext'
import type { GoogleHealthConnection } from '../hooks/useGoogleHealthConnection'
import { ConnectionStatusButton } from './ConnectionStatusButton'
import { IconMountain } from './icons'

interface TopbarProps {
  connection: GoogleHealthConnection
  onOpenProfile: () => void
}

export function Topbar({ connection, onOpenProfile }: TopbarProps) {
  const { user } = useAuth()

  // No profile-photo field on the account (accounts/schemas.py's
  // UserOut is just id/email/is_active/created_at) - always the initial
  // letter badge, never a photo.
  const avatarSrc: string | undefined = undefined
  const avatarInitial = (user?.email || 'W').charAt(0).toUpperCase()

  return (
    <header className="topbar">
      <div className="brand">
        <IconMountain className="icon brand-mark" />
        <span className="brand-name">WorldWalker</span>
      </div>

      <div className="topbar-actions">
        <ConnectionStatusButton connection={connection} />

        <button type="button" className="topbar-avatar-btn" aria-label="Your profile" onClick={onOpenProfile}>
          {avatarSrc ? <img src={avatarSrc} alt="" /> : <span>{avatarInitial}</span>}
        </button>
      </div>
    </header>
  )
}
