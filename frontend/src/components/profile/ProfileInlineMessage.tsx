// A short green/red confirmation line - "Profile photo updated
// successfully", "enter a new email address", etc. Shared by every
// ProfilePage.tsx field that needs one, so the color/weight/spacing stay
// identical no matter which field is showing it.

import type { ReactNode } from 'react'
import type { MessageTone } from '../../hooks/useTimedMessage'

interface ProfileInlineMessageProps {
  tone: MessageTone
  children: ReactNode
}

export function ProfileInlineMessage({ tone, children }: ProfileInlineMessageProps) {
  return (
    <p className={`profile-inline-message profile-inline-message-${tone}`} role={tone === 'error' ? 'alert' : 'status'}>
      {children}
    </p>
  )
}
