// Trips have no "favorite" field server-side yet (see types/trip.ts's
// TripSummary) - this keeps the My Walks dashboard's favorite toggle and
// "Favorites" filter working off a plain set of trip ids in localStorage,
// same private-to-this-browser pattern AppShell.tsx already uses for its
// resumable trip session. Swap this for a real backend field (and lose
// the per-browser limitation) if favoriting ever needs to follow a user
// across devices.

import { useCallback, useEffect, useState } from 'react'

const STORAGE_KEY = 'ww-favorite-trips'

function readStored(): Set<string> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return new Set()
    const parsed = JSON.parse(raw) as unknown
    return Array.isArray(parsed) ? new Set(parsed.filter((id): id is string => typeof id === 'string')) : new Set()
  } catch {
    return new Set()
  }
}

export function useFavoriteTrips() {
  const [favorites, setFavorites] = useState<Set<string>>(() => readStored())

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify([...favorites]))
    } catch {
      // Private window / blocked storage - favoriting just won't persist
      // across a reload, nothing crashes over it.
    }
  }, [favorites])

  const toggleFavorite = useCallback((tripId: string) => {
    setFavorites((prev) => {
      const next = new Set(prev)
      if (next.has(tripId)) next.delete(tripId)
      else next.add(tripId)
      return next
    })
  }, [])

  return { favorites, toggleFavorite }
}
