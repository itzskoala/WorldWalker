interface TripBackButtonProps {
  onClick: () => void
}

export function TripBackButton({ onClick }: TripBackButtonProps) {
  return (
    <button type="button" className="trip-map-btn trip-map-btn-dark trip-back-btn" aria-label="Back to My Journeys" onClick={onClick}>
      <svg className="icon" viewBox="0 0 24 24" fill="none">
        <path d="M19 12H5M11 6l-6 6 6 6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </button>
  )
}
