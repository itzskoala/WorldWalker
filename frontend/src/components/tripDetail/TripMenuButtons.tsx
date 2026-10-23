interface TripMenuButtonsProps {
  avatarInitial: string
  onMenu: () => void
  onAvatar: () => void
}

export function TripMenuButtons({ avatarInitial, onMenu, onAvatar }: TripMenuButtonsProps) {
  return (
    <div className="trip-overlay-row-end">
      <button type="button" className="trip-map-btn trip-map-btn-dark trip-menu-btn" aria-label="Menu" onClick={onMenu}>
        <svg className="icon" viewBox="0 0 24 24" fill="none">
          <circle cx="6" cy="6" r="1.7" fill="currentColor" />
          <circle cx="12" cy="6" r="1.7" fill="currentColor" />
          <circle cx="18" cy="6" r="1.7" fill="currentColor" />
          <circle cx="6" cy="12" r="1.7" fill="currentColor" />
          <circle cx="12" cy="12" r="1.7" fill="currentColor" />
          <circle cx="18" cy="12" r="1.7" fill="currentColor" />
          <circle cx="6" cy="18" r="1.7" fill="currentColor" />
          <circle cx="12" cy="18" r="1.7" fill="currentColor" />
          <circle cx="18" cy="18" r="1.7" fill="currentColor" />
        </svg>
      </button>
      <button type="button" className="trip-avatar-btn" aria-label="Your profile" onClick={onAvatar}>
        <span>{avatarInitial}</span>
      </button>
    </div>
  )
}
