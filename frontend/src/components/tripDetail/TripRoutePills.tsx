interface TripRoutePillsProps {
  from: string
  to: string
  isPaused: boolean
  planning: boolean
  percentComplete: number
}

export function TripRoutePills({ from, to, isPaused, planning, percentComplete }: TripRoutePillsProps) {
  return (
    <div className="trip-route-stack">
      <div className="trip-route-pills">
        <div className="trip-route-pill">
          <span className="trip-route-pill-dot trip-route-pill-dot--start" aria-hidden="true" />
          <span className="trip-route-pill-text">{from || '—'}</span>
        </div>
        <div className="trip-route-pill">
          <span className="trip-route-pill-dot trip-route-pill-dot--end" aria-hidden="true" />
          <span className="trip-route-pill-text">{to || '—'}</span>
        </div>
        <span className="trip-status-badge" hidden={!isPaused}>
          Paused
        </span>
      </div>
      <div className="trip-route-progress">
        {planning ? (
          // A 0%-filled bar here would look identical to a real
          // just-started walk, so this stands in for it instead.
          <span className="trip-route-progress-planning">
            <span className="spinner spinner-sm" aria-hidden="true" />
            Planning your route…
          </span>
        ) : (
          <>
            <span className="trip-card-progress trip-route-progress-bar">
              <span className="trip-card-progress-fill" style={{ width: `${percentComplete.toFixed(0)}%` }} />
            </span>
            <span className="trip-route-progress-pct">{percentComplete.toFixed(0)}%</span>
          </>
        )}
      </div>
    </div>
  )
}
