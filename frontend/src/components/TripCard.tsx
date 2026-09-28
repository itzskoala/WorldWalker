// Port of web/static/js/home.js's activeCardHtml()/completedCardHtml().
// Active/paused trips get the fuller card (thumbnail, progress, current
// checkpoint, steps, pause/resume); completed trips get a simpler one -
// same distinction the vanilla version drew from the summary's `status`.

import type { MouseEvent } from 'react'
import type { TripMapState, TripSummary, Coordinates } from '../types/trip'

const METERS_PER_MILE = 1609.344

function miles(meters: number): string {
  return `${(meters / METERS_PER_MILE).toFixed(1)} mi`
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

// checkpoints arrive already ordered by checkpoint_number (database/
// models.py's TripCheckpoint relationship order_by) - the last hit one is
// the most recently reached.
function currentCheckpointLabel(checkpoints: TripMapState['checkpoints']): string {
  const hit = checkpoints.filter((c) => c.hit)
  return hit.length ? hit[hit.length - 1].name : 'Not reached yet'
}

function ThumbnailSvg({ routePoints }: { routePoints: Coordinates[] }) {
  if (!routePoints || routePoints.length < 2) return <svg viewBox="0 0 52 52" />

  const lats = routePoints.map((p) => p.lat)
  const lngs = routePoints.map((p) => p.lng)
  const minLat = Math.min(...lats)
  const maxLat = Math.max(...lats)
  const minLng = Math.min(...lngs)
  const maxLng = Math.max(...lngs)
  const spanLat = maxLat - minLat || 1
  const spanLng = maxLng - minLng || 1
  const pad = 6
  const size = 52
  const points = routePoints
    .map((p) => {
      const x = pad + ((p.lng - minLng) / spanLng) * (size - pad * 2)
      const y = pad + (1 - (p.lat - minLat) / spanLat) * (size - pad * 2)
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')

  return (
    <svg viewBox={`0 0 ${size} ${size}`}>
      <polyline points={points} fill="none" stroke="var(--blue)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function RouteLine({ trip }: { trip: TripSummary }) {
  return (
    <div className="trip-card-route">
      <span>{trip.from_place}</span>
      <svg className="icon icon-sm" viewBox="0 0 24 24" fill="none">
        <path d="M5 12h14m0 0-5-5m5 5-5 5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      <span>{trip.to_place}</span>
    </div>
  )
}

function DeleteButton({ onClick }: { onClick: (e: MouseEvent) => void }) {
  return (
    <button type="button" className="trip-card-action is-delete" aria-label="Delete journey" onClick={onClick}>
      <svg className="icon icon-sm" viewBox="0 0 24 24" fill="none">
        <path
          d="M4 7h16M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2m-9 0 1 12a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1l1-12"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </button>
  )
}

interface ActiveTripCardProps {
  trip: TripSummary
  state: TripMapState
  onOpen: () => void
  onPauseResume: () => void
  onDelete: () => void
}

export function ActiveTripCard({ trip, state, onOpen, onPauseResume, onDelete }: ActiveTripCardProps) {
  const pct = Math.min(100, state.percent_complete).toFixed(0)
  const isPaused = state.status === 'paused'

  return (
    <li className="trip-card" onClick={onOpen}>
      <div className="trip-card-thumb">
        <ThumbnailSvg routePoints={trip.thumbnail_route} />
      </div>
      <div className="trip-card-body">
        <div className="trip-card-top">
          <RouteLine trip={trip} />
          <span className="trip-card-pct">{pct}%</span>
        </div>
        <span className="trip-card-progress">
          <span className="trip-card-progress-fill" style={{ width: `${pct}%` }} />
        </span>
        <div className="trip-card-meta">
          <span className="trip-card-checkpoint">📍 {currentCheckpointLabel(state.checkpoints)}</span>
          <span className="trip-card-steps">👣 {state.total_steps.toLocaleString()} steps</span>
        </div>
        {isPaused && <span className="trip-card-status is-paused">Paused</span>}
      </div>
      <div className="trip-card-actions">
        <button
          type="button"
          className="trip-card-action is-pause-resume"
          aria-label={isPaused ? 'Resume journey' : 'Pause journey'}
          onClick={(e) => {
            e.stopPropagation()
            onPauseResume()
          }}
        >
          {isPaused ? (
            <svg className="icon icon-sm" viewBox="0 0 24 24" fill="none">
              <path d="M7 5v14l12-7-12-7Z" fill="currentColor" />
            </svg>
          ) : (
            <svg className="icon icon-sm" viewBox="0 0 24 24" fill="none">
              <rect x="6" y="5" width="4" height="14" rx="1" fill="currentColor" />
              <rect x="14" y="5" width="4" height="14" rx="1" fill="currentColor" />
            </svg>
          )}
        </button>
        <DeleteButton
          onClick={(e) => {
            e.stopPropagation()
            onDelete()
          }}
        />
      </div>
    </li>
  )
}

interface CompletedTripCardProps {
  trip: TripSummary
  onOpen: () => void
  onDelete: () => void
}

// Completed trips are still clickable (opens Trip Detail as a read-only
// recap - see trip.js's own note that a finished journey has nothing
// left to pause/resume), same as active ones.
export function CompletedTripCard({ trip, onOpen, onDelete }: CompletedTripCardProps) {
  return (
    <li className="trip-card" onClick={onOpen}>
      <div className="trip-card-thumb">
        <ThumbnailSvg routePoints={trip.thumbnail_route} />
      </div>
      <div className="trip-card-body">
        <RouteLine trip={trip} />
        <div className="trip-card-stats">
          <span>
            {miles(trip.total_distance_m)} · {formatDate(trip.started_at)}
          </span>
        </div>
      </div>
      <div className="trip-card-actions">
        <DeleteButton
          onClick={(e) => {
            e.stopPropagation()
            onDelete()
          }}
        />
      </div>
    </li>
  )
}
