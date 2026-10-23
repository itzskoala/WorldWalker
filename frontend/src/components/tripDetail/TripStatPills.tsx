import { IconClock, IconFlag, IconFootsteps, IconRoute } from '../icons'
import { formatDistance, formatElapsedDuration, type DistanceUnit } from './tripFormat'

interface TripStatPillsProps {
  unit: DistanceUnit
  distanceWalkedM: number
  distanceRemainingM: number
  totalSteps: number
  todaySteps: number
  elapsedSeconds: number
  discoveredCheckpoints: number
  totalCheckpoints: number
}

export function TripStatPills({
  unit,
  distanceWalkedM,
  distanceRemainingM,
  totalSteps,
  todaySteps,
  elapsedSeconds,
  discoveredCheckpoints,
  totalCheckpoints,
}: TripStatPillsProps) {
  return (
    <>
      <div className="trip-stat-pill">
        <span className="trip-stat-pill-label">Distance Covered</span>
        <span className="trip-stat-pill-value">
          <IconRoute className="trip-stat-pill-icon" />
          {formatDistance(distanceWalkedM, unit)}
        </span>
      </div>
      <div className="trip-stat-pill">
        <span className="trip-stat-pill-label">Distance left</span>
        <span className="trip-stat-pill-value">
          <IconRoute className="trip-stat-pill-icon" />
          {formatDistance(distanceRemainingM, unit, 0)}
        </span>
      </div>
      <div className="trip-stat-pill">
        <span className="trip-stat-pill-label">Total Steps</span>
        <span className="trip-stat-pill-value">
          <IconFootsteps className="trip-stat-pill-icon" />
          {totalSteps.toLocaleString()}
        </span>
      </div>
      <div className="trip-stat-pill">
        <span className="trip-stat-pill-label">Today's Steps</span>
        <span className="trip-stat-pill-value">
          <IconFootsteps className="trip-stat-pill-icon" />
          {todaySteps.toLocaleString()}
        </span>
      </div>
      <div className="trip-stat-pill">
        <span className="trip-stat-pill-label">Time Elapsed</span>
        <span className="trip-stat-pill-value">
          <IconClock className="trip-stat-pill-icon" />
          {formatElapsedDuration(elapsedSeconds)}
        </span>
      </div>
      <div className="trip-stat-pill">
        <span className="trip-stat-pill-label">Checkpoints</span>
        <span className="trip-stat-pill-value">
          <IconFlag className="trip-stat-pill-icon" />
          {/* Discovered (proximity-revealed), not metadata-ready - see
              TripMapState.discovered_checkpoints. */}
          {discoveredCheckpoints}/{totalCheckpoints}
        </span>
      </div>
    </>
  )
}
