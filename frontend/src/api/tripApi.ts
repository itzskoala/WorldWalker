// Typed client for app.py's /api/places/* and /api/journey/* routes.

import type { Checkpoint, JourneyStartResponse, PlaceSuggestion, TripMapState, TripSummary } from '../types/trip'
import { apiFetch, parseErrorMessage } from './httpClient'

export async function searchPlaces(query: string): Promise<PlaceSuggestion[]> {
  const res = await fetch(`/api/places/search?q=${encodeURIComponent(query)}`, { credentials: 'include' })
  if (!res.ok) return []
  const data = (await res.json()) as { results: PlaceSuggestion[] }
  return data.results
}

export async function reversePlace(lat: number, lng: number): Promise<string> {
  const res = await fetch(`/api/places/reverse?lat=${lat}&lng=${lng}`, { credentials: 'include' })
  if (!res.ok) throw new Error(await parseErrorMessage(res, "Couldn't look up that location."))
  const data = (await res.json()) as { place: string }
  return data.place
}

export interface StartJourneyRequest {
  from_place: string
  to_place: string
  round_trip?: boolean
}

export async function startJourney(body: StartJourneyRequest): Promise<JourneyStartResponse> {
  const res = await apiFetch('/api/journey/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(await parseErrorMessage(res, "Couldn't start that walk — try again."))
  return res.json() as Promise<JourneyStartResponse>
}

export async function getJourneyState(tripId: string): Promise<TripMapState> {
  const res = await apiFetch(`/api/journey/state?trip_id=${tripId}`)
  if (!res.ok) throw new Error(await parseErrorMessage(res, "Couldn't load this trip."))
  return res.json() as Promise<TripMapState>
}

export async function listJourneys(): Promise<TripSummary[]> {
  const res = await apiFetch('/api/journey/list')
  if (!res.ok) throw new Error(await parseErrorMessage(res, "Couldn't load your journeys."))
  const data = (await res.json()) as { trips: TripSummary[] }
  return data.trips
}

export async function journeyStats(): Promise<{ lifetime_steps: number }> {
  const res = await apiFetch('/api/journey/stats')
  if (!res.ok) throw new Error(await parseErrorMessage(res, "Couldn't load your stats."))
  return res.json() as Promise<{ lifetime_steps: number }>
}

export async function pauseJourney(tripId: string): Promise<TripMapState> {
  const res = await apiFetch(`/api/journey/${tripId}/pause`, { method: 'POST' })
  if (!res.ok) throw new Error(await parseErrorMessage(res, "Couldn't pause this trip."))
  return res.json() as Promise<TripMapState>
}

export async function resumeJourney(tripId: string): Promise<TripMapState> {
  const res = await apiFetch(`/api/journey/${tripId}/resume`, { method: 'POST' })
  if (!res.ok) throw new Error(await parseErrorMessage(res, "Couldn't resume this trip."))
  return res.json() as Promise<TripMapState>
}

export async function deleteJourney(tripId: string): Promise<void> {
  const res = await apiFetch(`/api/journey/${tripId}`, { method: 'DELETE' })
  if (!res.ok) throw new Error(await parseErrorMessage(res, "Couldn't delete this trip."))
}

/** Multi-select delete from the trips panel - one request instead of
 * firing a DELETE per selected card. */
export async function deleteJourneys(tripIds: string[]): Promise<number> {
  const res = await apiFetch('/api/journey/delete', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ trip_ids: tripIds }),
  })
  if (!res.ok) throw new Error(await parseErrorMessage(res, "Couldn't delete those trips."))
  const data = (await res.json()) as { deleted: number }
  return data.deleted
}

export type TripCheckpointEvent =
  | { type: 'checkpoint_added'; checkpoint: Checkpoint }
  | { type: 'checkpoint_updated'; checkpoint: Checkpoint }
  | { type: 'checkpoints_ready' }

/** One SSE "event: ...\ndata: ...\n\n" block (already split on the blank
 * line separator by the reader loop below) into a typed event - null for
 * a bare ": keep-alive" comment line, which carries no "event:" field. */
function parseSSEBlock(raw: string): TripCheckpointEvent | null {
  let eventName = ''
  const dataLines: string[] = []
  for (const line of raw.split('\n')) {
    if (line.startsWith('event:')) eventName = line.slice('event:'.length).trim()
    else if (line.startsWith('data:')) dataLines.push(line.slice('data:'.length).trim())
  }
  if (!eventName) return null
  const data = dataLines.length ? JSON.parse(dataLines.join('\n')) : {}
  return { type: eventName, ...data } as TripCheckpointEvent
}

/** Live checkpoint_added/checkpoint_updated/checkpoints_ready events for
 * one trip while core/facade.py's generate_checkpoints_for_trip() (a
 * background task kicked off by startJourney()) discovers checkpoints and
 * generates their descriptions - see app.py's GET /api/journey/{trip_id}/
 * events. A plain `EventSource` can't attach the "Authorization: Bearer
 * ..." header this app's auth needs (frontend/src/api/httpClient.ts), so
 * this reads the same endpoint as a streamed fetch() response instead,
 * through the same apiFetch() every other authenticated call here uses.
 *
 * Returns an unsubscribe function - call it on unmount (or when starting
 * a different trip) to abort the underlying request; the server-side
 * generator's `finally` unsubscribes its EventManager listener the moment
 * that happens (app.py). */
export function subscribeToTripCheckpoints(tripId: string, onEvent: (event: TripCheckpointEvent) => void): () => void {
  const controller = new AbortController()

  void (async () => {
    let res: Response
    try {
      res = await apiFetch(`/api/journey/${tripId}/events`, { signal: controller.signal })
    } catch (err) {
      if ((err as Error).name !== 'AbortError') console.warn(`Couldn't open the checkpoint stream for trip ${tripId}:`, err)
      return
    }
    if (!res.ok || !res.body) return

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    try {
      while (true) {
        const { done, value } = await reader.read()
        if (done) return
        buffer += decoder.decode(value, { stream: true })

        let separatorIndex
        while ((separatorIndex = buffer.indexOf('\n\n')) !== -1) {
          const block = buffer.slice(0, separatorIndex)
          buffer = buffer.slice(separatorIndex + 2)
          const event = parseSSEBlock(block)
          if (event) onEvent(event)
        }
      }
    } catch (err) {
      if ((err as Error).name !== 'AbortError') console.warn(`Checkpoint stream for trip ${tripId} ended early:`, err)
    }
  })()

  return () => controller.abort()
}
