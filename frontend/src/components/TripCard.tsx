// Port of web/static/js/home.js's activeCardHtml()/completedCardHtml().
// Active/paused trips get the fuller card (thumbnail, progress, current
// checkpoint, steps, pause/resume); completed trips get a simpler one -
// same distinction the vanilla version drew from the summary's `status`.
//
// TripSummary now carries percent_complete/current_checkpoint_name/
// total_steps directly (core/facade.py's list_trips(), see
// types/trip.ts) so neither card fetches its own TripMapState anymore -
// this used to need one per active/paused trip just for those fields.
//
// Rename and "change photo" are newer, client-only affordances (see
// hooks/useTripNameOverrides.ts) layered onto this card's original
// layout - there's no trip_name column or photo-upload endpoint yet, so
// both are UI hook points for a future backend, same idea as
// components/walks/TripOverviewCard.tsx's versions of them.

import { useState } from 'react'
import type { KeyboardEvent, MouseEvent } from 'react'
import type { Coordinates, TripSummary } from '../types/trip'
import { formatDate, formatMiles, metersToMiles } from '../lib/format'
import { IconCamera, IconFootsteps, IconPencil, IconRoute, IconTrash } from './icons'

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

// Thumbnail + hover/focus "change photo" overlay - there's no photo
// upload endpoint yet (components/walks/TripThumb.tsx notes the same),
// so onEditThumbnail is a hook point for that future flow.
function TripThumbButton({ routePoints, onEditThumbnail }: { routePoints: Coordinates[]; onEditThumbnail: (e: MouseEvent) => void }) {
  return (
    <button type="button" className="trip-card-thumb-button" onClick={onEditThumbnail} aria-label="Change trip photo">
      <span className="trip-card-thumb">
        <ThumbnailSvg routePoints={routePoints} />
      </span>
      <span className="trip-card-thumb-edit">
        <IconCamera className="icon icon-sm" />
      </span>
    </button>
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

// The card's custom display name (the rename pencil's target) - falls
// back to trip.to_place, same convention as components/walks/
// TripOverviewCard.tsx, so a renamed trip reads consistently everywhere.
function TripNameRow({ displayName, onRename }: { displayName: string; onRename: (name: string) => void }) {
  const [isEditing, setIsEditing] = useState(false)
  const [draft, setDraft] = useState(displayName)

  function startEditing(e: MouseEvent) {
    e.stopPropagation()
    setDraft(displayName)
    setIsEditing(true)
  }

  function commit() {
    setIsEditing(false)
    onRename(draft)
  }

  function handleKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter') commit()
    else if (e.key === 'Escape') setIsEditing(false)
  }

  if (isEditing) {
    return (
      <input
        className="trip-card-name-input"
        value={draft}
        autoFocus
        onClick={(e) => e.stopPropagation()}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={handleKeyDown}
      />
    )
  }

  return (
    <span className="trip-card-name-row">
      <span className="trip-card-name">{displayName}</span>
      <button type="button" className="trip-card-edit-name" aria-label="Edit trip name" onClick={startEditing}>
        <IconPencil className="icon icon-sm" />
      </button>
    </span>
  )
}

function DeleteButton({ onClick }: { onClick: (e: MouseEvent) => void }) {
  return (
    <button type="button" className="trip-card-action is-delete" aria-label="Delete journey" onClick={onClick}>
      <IconTrash className="icon icon-sm" />
    </button>
  )
}

interface ActiveTripCardProps {
  trip: TripSummary
  displayName: string
  onOpen: () => void
  onPauseResume: () => void
  onDelete: () => void
  onRename: (name: string) => void
  onEditThumbnail: () => void
}

export function ActiveTripCard({ trip, displayName, onOpen, onPauseResume, onDelete, onRename, onEditThumbnail }: ActiveTripCardProps) {
  // percent_complete is the same field the Trip Detail map uses for its
  // own progress bar/pill (TripDetailPage.tsx's `pct`) - reusing it here
  // (rather than re-deriving a percentage from distance_walked_m/
  // total_distance_m) keeps the two screens' numbers identical and
  // avoids a client-side divide-by-zero if total_distance_m is ever 0.
  // Finite-guarded in case a malformed summary ever omits it.
  const pctValue = Number.isFinite(trip.percent_complete) ? Math.min(100, Math.max(0, trip.percent_complete)) : 0
  const pct = pctValue.toFixed(0)
  const hasTotalDistance = trip.total_distance_m > 0
  const milesWalked = metersToMiles(trip.distance_walked_m || 0).toFixed(1)
  const milesTotal = metersToMiles(trip.total_distance_m || 0).toFixed(1)
  const isPaused = trip.status === 'paused'

  function stop(handler: () => void) {
    return (e: MouseEvent) => {
      e.stopPropagation()
      handler()
    }
  }

  return (
    <li className="trip-card" onClick={onOpen}>
      <TripThumbButton routePoints={trip.thumbnail_route} onEditThumbnail={stop(onEditThumbnail)} />
      <div className="trip-card-body">
        <TripNameRow displayName={displayName} onRename={onRename} />
        <div className="trip-card-top">
          <RouteLine trip={trip} />
          <span className="trip-card-pct">{pct}%</span>
        </div>
        <span className="trip-card-progress">
          <span className="trip-card-progress-fill" style={{ width: `${pct}%` }} />
        </span>
        <div className="trip-card-meta">
          {/* Distance covered / total route distance, same unit and one
              decimal place as formatMiles()/TripDetailPage.tsx's own
              distance stats - replaces the old "Not reached yet"
              checkpoint-name placeholder with real progress (keeps the
              .trip-card-checkpoint class so no CSS changes). Falls back
              to just the distance walked when total_distance_m is
              missing/zero, rather than showing a meaningless "/ 0.0 mi". */}
          <span className="trip-card-checkpoint">
            <IconRoute className="icon icon-sm" />
            {hasTotalDistance ? `${milesWalked} / ${milesTotal} mi · ${pct}%` : `${milesWalked} mi`}
          </span>
          <span className="trip-card-steps">
            <IconFootsteps className="icon icon-sm" />
            {trip.total_steps.toLocaleString()} steps
          </span>
        </div>
        {isPaused && <span className="trip-card-status is-paused">Paused</span>}
      </div>
      <div className="trip-card-actions">
        <button
          type="button"
          className="trip-card-action is-pause-resume"
          aria-label={isPaused ? 'Resume journey' : 'Pause journey'}
          onClick={stop(onPauseResume)}
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
        <DeleteButton onClick={stop(onDelete)} />
      </div>
    </li>
  )
}

interface CompletedTripCardProps {
  trip: TripSummary
  displayName: string
  onOpen: () => void
  onDelete: () => void
  onRename: (name: string) => void
  onEditThumbnail: () => void
}

// Completed trips are still clickable (opens Trip Detail as a read-only
// recap - see trip.js's own note that a finished journey has nothing
// left to pause/resume), same as active ones.
export function CompletedTripCard({ trip, displayName, onOpen, onDelete, onRename, onEditThumbnail }: CompletedTripCardProps) {
  function stop(handler: () => void) {
    return (e: MouseEvent) => {
      e.stopPropagation()
      handler()
    }
  }

  return (
    <li className="trip-card" onClick={onOpen}>
      <TripThumbButton routePoints={trip.thumbnail_route} onEditThumbnail={stop(onEditThumbnail)} />
      <div className="trip-card-body">
        <TripNameRow displayName={displayName} onRename={onRename} />
        <RouteLine trip={trip} />
        <div className="trip-card-stats">
          <span>
            {formatMiles(trip.total_distance_m)} · {formatDate(trip.started_at)}
          </span>
        </div>
      </div>
      <div className="trip-card-actions">
        <DeleteButton onClick={stop(onDelete)} />
      </div>
    </li>
  )
}
