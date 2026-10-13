// The "All Trips" list item - its own component (not a TripRow.tsx
// variant anymore) now that it carries editing affordances Recent
// Activity's lighter row doesn't need: an inline trip-name rename and a
// thumbnail hover state for swapping the photo. TripRow.tsx stays the
// plain compact row for Recent Activity.

import { useState } from 'react'
import type { KeyboardEvent, MouseEvent } from 'react'
import type { TripSummary } from '../../types/trip'
import { estimatedDurationSeconds, formatDate, formatDuration, formatKm } from '../../lib/format'
import { IconCamera, IconCheck, IconChevronRight, IconClock, IconFootsteps, IconHeart, IconPencil, IconRoute, IconTrash } from '../icons'
import { TripThumb } from './TripThumb'

const STATUS_LABEL: Record<TripSummary['status'], string> = {
  completed: 'Completed',
  active: 'In Progress',
  paused: 'Paused',
}

function StatusBadge({ status }: { status: TripSummary['status'] }) {
  return (
    <span className={`walks-status-badge is-${status}`}>
      {status === 'completed' && <IconCheck className="icon icon-sm" />}
      {STATUS_LABEL[status]}
    </span>
  )
}

interface TripOverviewCardProps {
  trip: TripSummary
  displayName: string
  isFavorite: boolean
  onToggleFavorite: () => void
  onRename: (name: string) => void
  onEditThumbnail: () => void
  onOpen: () => void
  onDelete: () => void
}

export function TripOverviewCard({ trip, displayName, isFavorite, onToggleFavorite, onRename, onEditThumbnail, onOpen, onDelete }: TripOverviewCardProps) {
  const [isEditingName, setIsEditingName] = useState(false)
  const [draftName, setDraftName] = useState(displayName)
  const seconds = estimatedDurationSeconds(trip.distance_walked_m)

  function stop(handler: () => void) {
    return (e: MouseEvent) => {
      e.stopPropagation()
      handler()
    }
  }

  function startEditingName() {
    setDraftName(displayName)
    setIsEditingName(true)
  }

  function commitName() {
    setIsEditingName(false)
    onRename(draftName)
  }

  function handleNameKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter') commitName()
    else if (e.key === 'Escape') setIsEditingName(false)
  }

  return (
    <li className="walks-trip-row is-full" onClick={isEditingName ? undefined : onOpen}>
      {/* Thumbnail: a dark scrim + camera icon appears on hover/focus
          (.walks-thumb-edit, see style.css) indicating this is clickable
          to change the trip's photo - there's no photo upload endpoint
          yet, so onEditThumbnail is a hook point for that future flow. */}
      <button type="button" className="walks-thumb-button" onClick={stop(onEditThumbnail)} aria-label="Change trip photo">
        <TripThumb routePoints={trip.thumbnail_route} />
        <span className="walks-thumb-edit">
          <IconCamera className="icon icon-sm" />
        </span>
      </button>

      <div className="walks-row-body">
        {isEditingName ? (
          <input
            className="walks-row-title-input"
            value={draftName}
            autoFocus
            onClick={(e) => e.stopPropagation()}
            onChange={(e) => setDraftName(e.target.value)}
            onBlur={commitName}
            onKeyDown={handleNameKeyDown}
          />
        ) : (
          <span className="walks-row-title-line">
            <span className="walks-row-title">{displayName}</span>
            <button type="button" className="walks-row-edit-name" aria-label="Edit trip name" onClick={stop(startEditingName)}>
              <IconPencil className="icon icon-sm" />
            </button>
          </span>
        )}
        <span className="walks-row-location">From {trip.from_place}</span>
      </div>

      <div className="walks-row-metrics">
        <span className="walks-row-metric">
          <IconRoute className="icon icon-sm" />
          {formatKm(trip.distance_walked_m)} / {formatKm(trip.total_distance_m)}
        </span>
        <span className="walks-row-metric">
          <IconClock className="icon icon-sm" />
          {formatDuration(seconds)}
        </span>
        <span className="walks-row-metric">
          <IconFootsteps className="icon icon-sm" />
          {trip.total_steps.toLocaleString()} steps
        </span>
      </div>

      <StatusBadge status={trip.status} />
      <span className="walks-row-date">{formatDate(trip.started_at)}</span>

      <div className="walks-row-actions">
        <button
          type="button"
          className={`walks-row-action is-favorite${isFavorite ? ' is-on' : ''}`}
          aria-label={isFavorite ? 'Remove from favorites' : 'Add to favorites'}
          aria-pressed={isFavorite}
          onClick={stop(onToggleFavorite)}
        >
          <IconHeart className="icon icon-sm" filled={isFavorite} />
        </button>
        <button type="button" className="walks-row-action is-delete" aria-label="Delete journey" onClick={stop(onDelete)}>
          <IconTrash className="icon icon-sm" />
        </button>
      </div>

      {/* Opens this trip's map view (HomePage.tsx's onOpenTrip ->
          AppShell.tsx swaps in TripDetailPage) - a route change today,
          not a modal, but this is the one spot that decision would
          change if a modal became the preferred UX instead. */}
      <IconChevronRight className="icon icon-sm walks-row-chevron" />
    </li>
  )
}
