// A one-shot status message ("saved", "try again") that clears itself a
// few seconds after being set, instead of lingering on screen forever.
// Shared by ProfileAvatarUpload.tsx, ProfileEmailField.tsx, and
// ProfilePage.tsx's own submit feedback - anywhere a brief green/red
// confirmation follows an action.

import { useEffect, useRef, useState } from 'react'

export type MessageTone = 'success' | 'error'

export interface TimedMessage {
  tone: MessageTone
  text: string
}

const DISMISS_AFTER_MS = 4000

export function useTimedMessage() {
  const [message, setMessageState] = useState<TimedMessage | null>(null)
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(
    () => () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current)
    },
    [],
  )

  function setMessage(next: TimedMessage | null) {
    if (timeoutRef.current) clearTimeout(timeoutRef.current)
    setMessageState(next)
    if (next) {
      timeoutRef.current = setTimeout(() => setMessageState(null), DISMISS_AFTER_MS)
    }
  }

  return [message, setMessage] as const
}
