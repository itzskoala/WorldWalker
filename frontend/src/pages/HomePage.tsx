// Port of web/static/js/home.js - "My Journeys": every active/paused trip
// as a prominent card, every completed trip as a simpler one below it.
// Re-fetches whenever this tab becomes active (the `active` prop toggling
// true) - same trigger as the vanilla version's "ww:screen-shown" listener,
// so a trip started/paused/finished while Trip Detail was up is never
// shown stale here.

import { useCallback, useEffect, useState } from 'react'
import { ActiveTripCard, CompletedTripCard } from '../components/TripCard'
import { deleteJourney, getJourneyState, listJourneys, pauseJourney, resumeJourney } from '../api/tripApi'
import type { TripMapState, TripSummary } from '../types/trip'

const CURRENT_STATUSES = new Set(['active', 'paused'])

interface HomePageProps {
  active: boolean
  onOpenTrip: (tripId: string) => void
}

export function HomePage({ active, onOpenTrip }: HomePageProps) {
  const [trips, setTrips] = useState<TripSummary[]>([])
  const [activeStates, setActiveStates] = useState<Record<string, TripMapState>>({})
  const [loaded, setLoaded] = useState(false)

  const load = useCallback(async () => {
    let list: TripSummary[]
    try {
      list = await listJourneys()
    } catch (err) {
      console.warn("Couldn't load your journeys:", err)
      return
    }
    setTrips(list)
    setLoaded(true)

    // Each active/paused trip needs its own full state fetch (for
    // checkpoints + total_steps) - fine in practice, a personal walking
    // app has a handful of these going at once, not hundreds.
    const activeTrips = list.filter((t) => CURRENT_STATUSES.has(t.status))
    const entries = await Promise.all(
      activeTrips.map(async (trip): Promise<[string, TripMapState] | null> => {
        try {
          return [trip.trip_id, await getJourneyState(trip.trip_id)]
        } catch {
          return null
        }
      }),
    )
    setActiveStates(Object.fromEntries(entries.filter((e): e is [string, TripMapState] => e !== null)))
  }, [])

  useEffect(() => {
    if (active) load()
  }, [active, load])

  async function handlePauseResume(trip: TripSummary) {
    try {
      if (trip.status === 'paused') await resumeJourney(trip.trip_id)
      else await pauseJourney(trip.trip_id)
    } catch (err) {
      console.warn('pause/resume failed:', err)
    }
    load()
  }

  async function handleDelete(tripId: string) {
    try {
      await deleteJourney(tripId)
    } catch (err) {
      console.warn('delete failed:', err)
    }
    load()
  }

  const activeTrips = trips.filter((t) => CURRENT_STATUSES.has(t.status))
  const completedTrips = trips.filter((t) => t.status === 'completed')

  return (
    <section className="screen" id="screen-home" aria-label="My Journeys">
      <div className="screen-inner">
        <div className="screen-header">
          <h1 className="screen-title">My Journeys</h1>
        </div>

        <section className="trips-group">
          <h2 className="trips-group-title">Active</h2>
          <ul className="trips-list">
            {activeTrips.map((trip) =>
              activeStates[trip.trip_id] ? (
                <ActiveTripCard
                  key={trip.trip_id}
                  trip={trip}
                  state={activeStates[trip.trip_id]}
                  onOpen={() => onOpenTrip(trip.trip_id)}
                  onPauseResume={() => handlePauseResume(trip)}
                  onDelete={() => handleDelete(trip.trip_id)}
                />
              ) : null,
            )}
          </ul>
          {loaded && activeTrips.length === 0 && (
            <p className="trips-empty">No active journeys yet — plan one on the Create tab.</p>
          )}
        </section>

        <section className="trips-group">
          <h2 className="trips-group-title">Completed</h2>
          <ul className="trips-list">
            {completedTrips.map((trip) => (
              <CompletedTripCard key={trip.trip_id} trip={trip} onOpen={() => onOpenTrip(trip.trip_id)} onDelete={() => handleDelete(trip.trip_id)} />
            ))}
          </ul>
          {loaded && completedTrips.length === 0 && <p className="trips-empty">Finished journeys will show up here.</p>}
        </section>
      </div>
    </section>
  )
}
