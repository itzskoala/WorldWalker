// Port of web/static/js/home.js - "My Journeys": every active/paused trip
// as a prominent card, every completed trip as a simpler one below it.
// Re-fetches whenever this tab becomes active (the `active` prop toggling
// true) - same trigger as the vanilla version's "ww:screen-shown" listener,
// so a trip started/paused/finished while Trip Detail was up is never
// shown stale here.
//
// TripSummary carries percent_complete/current_checkpoint_name/
// total_steps directly now (core/facade.py's list_trips(), see
// types/trip.ts) - this used to also fetch a full TripMapState per
// active/paused trip just for those three fields; that extra per-trip
// fetch is gone now that the backend computes them directly.

import { useCallback, useEffect, useState } from 'react'
import { ActiveTripCard, CompletedTripCard } from '../components/TripCard'
import { useTripNameOverrides } from '../hooks/useTripNameOverrides'
import { deleteJourney, listJourneys, pauseJourney, resumeJourney } from '../api/tripApi'
import type { TripStatus, TripSummary } from '../types/trip'

const CURRENT_STATUSES = new Set(['active', 'paused'])

// A status filter, purely a display-side narrowing of the already-loaded
// `trips` list below - no extra fetch, no mutation, so switching pills
// can never modify or delete a walk. 'all' (the default) renders exactly
// the original two-group Active/Completed layout; any specific status
// instead collapses to one group so "Paused" never reads as a subset of
// an "Active" heading that no longer matches what's listed under it.
type StatusFilter = 'all' | TripStatus

const STATUS_FILTERS: { value: StatusFilter; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'active', label: 'In Progress' },
  { value: 'paused', label: 'Paused' },
  { value: 'completed', label: 'Completed' },
]

interface HomePageProps {
  active: boolean
  onOpenTrip: (tripId: string) => void
  onExplore: () => void
}

export function HomePage({ active, onOpenTrip, onExplore }: HomePageProps) {
  const [trips, setTrips] = useState<TripSummary[]>([])
  const [loaded, setLoaded] = useState(false)
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')
  const { nameOverrides, renameTrip } = useTripNameOverrides()

  const load = useCallback(async () => {
    try {
      setTrips(await listJourneys())
    } catch (err) {
      console.warn("Couldn't load your journeys:", err)
      return
    }
    setLoaded(true)
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

  // There's no photo-upload endpoint for a trip yet (thumbnails are a
  // route sparkline, not a stored photo - see components/walks/
  // TripThumb.tsx) - this is a placeholder hook point for that flow,
  // same idea as components/walks/TripOverviewCard.tsx's own version.
  function handleEditThumbnail(tripId: string) {
    console.info(`TODO: open a photo-upload flow for trip ${tripId} once the backend supports one.`)
  }

  const showActiveGroup = statusFilter !== 'completed'
  const showCompletedGroup = statusFilter === 'all' || statusFilter === 'completed'
  const activeTrips = trips.filter((t) => CURRENT_STATUSES.has(t.status) && (statusFilter === 'all' || t.status === statusFilter))
  const completedTrips = showCompletedGroup ? trips.filter((t) => t.status === 'completed') : []
  const activeGroupTitle = statusFilter === 'active' ? 'In Progress' : statusFilter === 'paused' ? 'Paused' : 'Active'

  return (
    <section className="screen" id="screen-home" aria-label="My Journeys">
      <div className="screen-inner">
        <div className="screen-header">
          <h1 className="screen-title">My Journeys</h1>
        </div>

        <div className="walks-filter-row" role="group" aria-label="Filter journeys by status">
          {STATUS_FILTERS.map(({ value, label }) => (
            <button
              key={value}
              type="button"
              className={`walks-filter-pill${statusFilter === value ? ' is-active' : ''}`}
              aria-pressed={statusFilter === value}
              onClick={() => setStatusFilter(value)}
            >
              {label}
            </button>
          ))}
        </div>

        {showActiveGroup && (
          <section className="trips-group">
            <h2 className="trips-group-title">{activeGroupTitle}</h2>
            <ul className="trips-list">
              {activeTrips.map((trip) => (
                <ActiveTripCard
                  key={trip.trip_id}
                  trip={trip}
                  displayName={nameOverrides[trip.trip_id] ?? trip.to_place}
                  onOpen={() => onOpenTrip(trip.trip_id)}
                  onPauseResume={() => handlePauseResume(trip)}
                  onDelete={() => handleDelete(trip.trip_id)}
                  onRename={(name) => renameTrip(trip.trip_id, name)}
                  onEditThumbnail={() => handleEditThumbnail(trip.trip_id)}
                />
              ))}
            </ul>
            {loaded && activeTrips.length === 0 && (
              <p className="trips-empty">
                {statusFilter === 'all' ? (
                  <>
                    No active journeys yet — plan one on the{' '}
                    <button type="button" className="trips-empty-link" onClick={onExplore}>
                      Explore
                    </button>{' '}
                    tab.
                  </>
                ) : (
                  `No ${activeGroupTitle.toLowerCase()} journeys right now.`
                )}
              </p>
            )}
          </section>
        )}

        {showCompletedGroup && (
          <section className="trips-group">
            <h2 className="trips-group-title">Completed</h2>
            <ul className="trips-list">
              {completedTrips.map((trip) => (
                <CompletedTripCard
                  key={trip.trip_id}
                  trip={trip}
                  displayName={nameOverrides[trip.trip_id] ?? trip.to_place}
                  onOpen={() => onOpenTrip(trip.trip_id)}
                  onDelete={() => handleDelete(trip.trip_id)}
                  onRename={(name) => renameTrip(trip.trip_id, name)}
                  onEditThumbnail={() => handleEditThumbnail(trip.trip_id)}
                />
              ))}
            </ul>
            {loaded && completedTrips.length === 0 && <p className="trips-empty">Finished journeys will show up here.</p>}
          </section>
        )}
      </div>
    </section>
  )
}
