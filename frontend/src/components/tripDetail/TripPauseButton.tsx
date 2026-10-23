interface TripPauseButtonProps {
  isPaused: boolean
  disabled: boolean
  onClick: () => void
}

export function TripPauseButton({ isPaused, disabled, onClick }: TripPauseButtonProps) {
  return (
    <button
      type="button"
      className={`trip-map-btn trip-map-btn-dark btn-pause${isPaused ? ' is-paused' : ''}`}
      aria-label={isPaused ? 'Resume' : 'Pause'}
      disabled={disabled}
      onClick={onClick}
    >
      {isPaused ? (
        <svg className="icon icon-resume" viewBox="0 0 24 24" fill="none">
          <path d="M7 5v14l12-7-12-7Z" fill="currentColor" />
        </svg>
      ) : (
        <svg className="icon icon-pause" viewBox="0 0 24 24" fill="none">
          <rect x="6" y="5" width="4" height="14" rx="1" fill="currentColor" />
          <rect x="14" y="5" width="4" height="14" rx="1" fill="currentColor" />
        </svg>
      )}
    </button>
  )
}
