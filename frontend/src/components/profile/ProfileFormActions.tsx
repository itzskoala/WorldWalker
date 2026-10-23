// Bottom row of ProfilePage.tsx's account form - the submit button, the
// (disabled, no backend support yet) account-deletion link, and the
// green/red confirmation line underneath once a submit resolves.

import type { TimedMessage } from '../../hooks/useTimedMessage'
import { ProfileInlineMessage } from './ProfileInlineMessage'

interface ProfileFormActionsProps {
  saving: boolean
  message: TimedMessage | null
}

export function ProfileFormActions({ saving, message }: ProfileFormActionsProps) {
  return (
    <div className="profile-page-actions-wrap">
      <div className="profile-page-actions">
        <button type="submit" className="profile-page-submit" disabled={saving}>
          {saving ? 'Saving…' : 'Update profile'}
        </button>
        <button type="button" className="profile-page-delete" disabled>
          Delete account
        </button>
      </div>
      {message && <ProfileInlineMessage tone={message.tone}>{message.text}</ProfileInlineMessage>}
    </div>
  )
}
