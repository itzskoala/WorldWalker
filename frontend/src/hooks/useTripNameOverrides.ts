// A trip has no real editable "name" server-side - the Trip Overview
// Card's title is just trip.to_place (see types/trip.ts's TripSummary;
// there's no trip_name column, though [[future_multi_trip_support]]'s
// own memory notes one may exist one day). Until then, the card's "edit
// name" pencil writes a display-only override into localStorage, same
// per-browser pattern as useFavoriteTrips.ts, keyed by trip id. Swap this
// for a real PATCH /api/journey/{id} rename endpoint if one ever exists.

import { useCallback, useEffect, useState } from 'react'

const STORAGE_KEY = 'ww-trip-name-overrides'

function readStored(): Record<string, string> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return {}
    const parsed = JSON.parse(raw) as unknown
    if (!parsed || typeof parsed !== 'object') return {}
    const entries = Object.entries(parsed as Record<string, unknown>).filter((entry): entry is [string, string] => typeof entry[1] === 'string')
    return Object.fromEntries(entries)
  } catch {
    return {}
  }
}

export function useTripNameOverrides() {
  const [nameOverrides, setNameOverrides] = useState<Record<string, string>>(() => readStored())

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(nameOverrides))
    } catch {
      // Private window / blocked storage - the rename just won't persist
      // across a reload, nothing crashes over it.
    }
  }, [nameOverrides])

  const renameTrip = useCallback((tripId: string, name: string) => {
    setNameOverrides((prev) => {
      const trimmed = name.trim()
      if (!trimmed) {
        if (!(tripId in prev)) return prev
        const next = { ...prev }
        delete next[tripId]
        return next
      }
      return { ...prev, [tripId]: trimmed }
    })
  }, [])

  return { nameOverrides, renameTrip }
}
