// Avatar circle + edit button + hidden file input, for ProfilePage.tsx's
// account form. Resizes the picked image client-side (a plain <canvas>,
// longest side capped) before handing the result up as a data URL -
// there's no S3/Blob storage wired up in this codebase, so the photo is
// persisted as a plain string in the same profile_photo column every
// other field already goes through (accounts/router.py's PATCH /auth/me,
// which commits it via user_profile/profile_page.py's set_profile_photo
// - api/authApi.ts's ProfileUpdate). onUpload rejecting (bad file,
// network failure, anything) always collapses to the same short "Try
// again." - the user doesn't need to know which step failed.

import { useRef, useState, type ChangeEvent } from 'react'
import { IconPencil } from '../icons'
import { useTimedMessage } from '../../hooks/useTimedMessage'
import { ProfileInlineMessage } from './ProfileInlineMessage'

const MAX_DIMENSION = 480
const JPEG_QUALITY = 0.85

function resizeToDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onerror = () => reject(new Error('Try again.'))
    reader.onload = () => {
      const img = new Image()
      img.onerror = () => reject(new Error('Try again.'))
      img.onload = () => {
        const scale = Math.min(1, MAX_DIMENSION / Math.max(img.width, img.height))
        const canvas = document.createElement('canvas')
        canvas.width = Math.round(img.width * scale)
        canvas.height = Math.round(img.height * scale)
        const ctx = canvas.getContext('2d')
        if (!ctx) {
          reject(new Error('Try again.'))
          return
        }
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height)
        resolve(canvas.toDataURL('image/jpeg', JPEG_QUALITY))
      }
      img.src = reader.result as string
    }
    reader.readAsDataURL(file)
  })
}

interface ProfileAvatarUploadProps {
  photoUrl: string | null | undefined
  fallbackLetter: string
  onUpload: (dataUrl: string) => Promise<void>
}

export function ProfileAvatarUpload({ photoUrl, fallbackLetter, onUpload }: ProfileAvatarUploadProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useTimedMessage()

  async function handleFile(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    if (!file.type.startsWith('image/')) {
      setMessage({ tone: 'error', text: 'Try again.' })
      return
    }
    setMessage(null)
    setSaving(true)
    try {
      const dataUrl = await resizeToDataUrl(file)
      await onUpload(dataUrl)
      setMessage({ tone: 'success', text: 'Profile photo updated successfully' })
    } catch {
      setMessage({ tone: 'error', text: 'Try again.' })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className={`profile-page-avatar-wrap${saving ? ' is-saving' : ''}`}>
      {photoUrl ? (
        <img className="profile-page-avatar-photo" src={photoUrl} alt="" />
      ) : (
        <span className="profile-page-avatar-fallback" aria-hidden="true">
          {fallbackLetter}
        </span>
      )}
      <button
        type="button"
        className="profile-page-avatar-edit"
        aria-label="Change profile photo"
        disabled={saving}
        onClick={() => inputRef.current?.click()}
      >
        <IconPencil className="icon icon-sm" />
      </button>
      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        className="profile-page-avatar-input"
        aria-hidden="true"
        tabIndex={-1}
        onChange={handleFile}
      />
      {message && (
        <div className="profile-page-avatar-message">
          <ProfileInlineMessage tone={message.tone}>{message.text}</ProfileInlineMessage>
        </div>
      )}
    </div>
  )
}
