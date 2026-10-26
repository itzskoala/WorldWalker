import type { User } from '../types/user'

const STORAGE_KEY = 'ww-last-user'

export interface LastUser {
  email: string
  name: string
  profilePhoto: string | null
}

export function rememberLastUser(user: User): void {
  const name = user.f_name || user.username || user.email.split('@')[0]
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ email: user.email, name, profilePhoto: user.profile_photo }))
  } catch {
    // localStorage can throw in private/blocked contexts - returning-user
    // UX is a nicety, never required for login to work.
  }
}

export function getLastUser(): LastUser | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? (JSON.parse(raw) as LastUser) : null
  } catch {
    return null
  }
}

export function forgetLastUser(): void {
  try {
    localStorage.removeItem(STORAGE_KEY)
  } catch {
    // see rememberLastUser
  }
}
