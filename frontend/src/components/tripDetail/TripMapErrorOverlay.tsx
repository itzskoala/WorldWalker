interface TripMapErrorOverlayProps {
  message: string | null
  onRetry: () => void
}

export function TripMapErrorOverlay({ message, onRetry }: TripMapErrorOverlayProps) {
  return (
    <div className="trip-map-loading is-error" hidden={!message} onClick={onRetry}>
      <svg className="trip-map-loading-error-icon" viewBox="0 0 24 24" fill="none">
        <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.8" />
        <path d="M12 8v5M12 16h.01" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      </svg>
      <p>{message}</p>
    </div>
  )
}
