// Recent Activity's row - a plain, compact row (thumbnail, title,
// location, distance, time, favorite/delete, chevron). The All Trips
// list item carries more (editable name, editable thumbnail, a status
// badge, current/total mileage) and lives in its own TripOverviewCard.tsx
// instead of as a variant here, now that the two have diverged enough to
// not share much markup.

import type { MouseEvent } from 'react'
import type { TripSummary } from '../../types/trip'
import { estimatedDurationSeconds, formatDuration, formatMiles } from '../../lib/format'
import { IconChevronRight, IconClock, IconHeart, IconRoute, IconTrash } from '../icons'
import { TripThumb } from './TripThumb'

interface TripRowProps {
  trip: TripSummary
  isFavorite: boolean
  onToggleFavorite: () => void
  onOpen: () => void
  onDelete: () => void
}

export function TripRow({ trip, isFavorite, onToggleFavorite, onOpen, onDelete }: TripRowProps) {
  const seconds = estimatedDurationSeconds(trip.distance_walked_m)

  function stop(handler: () => void) {
    return (e: MouseEvent) => {
      e.stopPropagation()
      handler()
    }
  }

  return (
    <li className="walks-trip-row is-compact" onClick={onOpen}>
      <TripThumb routePoints={trip.thumbnail_route} />

      <div className="walks-row-body">
        <span className="walks-row-title">{trip.to_place}</span>
        <span className="walks-row-location">From {trip.from_place}</span>
        <div className="walks-row-metrics">
          <span className="walks-row-metric">
            <IconRoute className="icon icon-sm" />
            {formatMiles(trip.distance_walked_m)}
          </span>
          <span className="walks-row-metric">
            <IconClock className="icon icon-sm" />
            {formatDuration(seconds)}
          </span>
        </div>
      </div>

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

      <IconChevronRight className="icon icon-sm walks-row-chevron" />
    </li>
  )
}
