// Small line-art icon set shared by the trip dashboard (TripDetailPage.tsx)
// and the home-page trip cards (TripCard.tsx) - replaces emoji glyphs
// (steps/distance/time/checkpoint markers) with the same stroke-based
// SVG language already used for the back arrow, pause/resume, and delete
// icons elsewhere in this app, instead of mixing emoji + line icons.

interface IconProps {
  className?: string
}

export function IconRoute({ className = 'icon icon-sm' }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M8 3 5 21M16 3l3 18" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M10.3 9h3.4M9.4 15h5.2" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  )
}

// An ascending-stairs glyph rather than a literal footprint - at the
// ~13px this renders at inline with stat text, two small rotated
// ellipses (an actual footprint shape) read as a degree/percent symbol
// instead, which is actively misleading next to a step count. Stairs
// stay legible and unambiguous at that size and are a common "steps"
// pictogram in fitness UIs.
export function IconFootsteps({ className = 'icon icon-sm' }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M4 20v-4h4v-4h4V8h4V4h4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export function IconClock({ className = 'icon icon-sm' }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="8.5" stroke="currentColor" strokeWidth="1.8" />
      <path d="M12 7.5V12l3 2" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export function IconFlag({ className = 'icon icon-sm' }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M6 21V3" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      <path d="M6 4.2h10.5l-2.6 3.3 2.6 3.3H6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export function IconPin({ className = 'icon icon-sm' }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M12 21s7-7.37 7-12a7 7 0 1 0-14 0c0 4.63 7 12 7 12Z" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
      <circle cx="12" cy="9" r="2.2" stroke="currentColor" strokeWidth="1.8" />
    </svg>
  )
}

export function IconCalendar({ className = 'icon icon-sm' }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="4" y="5.5" width="16" height="15" rx="2" stroke="currentColor" strokeWidth="1.8" />
      <path d="M4 9.5h16M8 3.5v4M16 3.5v4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  )
}

export function IconTrophy({ className = 'icon icon-sm' }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M7 4h10v5a5 5 0 0 1-10 0V4Z"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
      <path d="M7 5.5H4a3 3 0 0 0 3 5.5M17 5.5h3a3 3 0 0 1-3 5.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      <path d="M12 14v3m-3.5 3h7M9 20h6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  )
}

export function IconImages({ className = 'icon icon-sm' }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="2.5" y="5.5" width="14.5" height="13" rx="2" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
      <path d="m4.5 15 3.3-3.3a1.5 1.5 0 0 1 2.1 0l4.1 4.1" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="7.3" cy="9.3" r="1.3" stroke="currentColor" strokeWidth="1.8" />
      <path d="M20.5 8v8.5a2 2 0 0 1-2 2H9" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  )
}

export function IconHeart({ className = 'icon icon-sm', filled = false }: IconProps & { filled?: boolean }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M12 20.3S3.5 15 3.5 9.1A4.6 4.6 0 0 1 12 6.4a4.6 4.6 0 0 1 8.5 2.7c0 5.9-8.5 11.2-8.5 11.2Z"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
        fill={filled ? 'currentColor' : 'none'}
      />
    </svg>
  )
}

export function IconCamera({ className = 'icon icon-sm' }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M4 8.5h3l1.3-2h7.4l1.3 2h3v11H4v-11Z" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
      <circle cx="12" cy="14" r="3.4" stroke="currentColor" strokeWidth="1.8" />
    </svg>
  )
}

export function IconTrash({ className = 'icon icon-sm' }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M4 7h16M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2m-9 0 1 12a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1l1-12"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

export function IconChevronRight({ className = 'icon icon-sm' }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="m9.5 5.5 7 6.5-7 6.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export function IconMountain({ className = 'icon icon-sm' }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="m3 18 6-9 4 5.5 2-2.5 6 6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export function IconCompass({ className = 'icon icon-sm' }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.8" />
      <path d="m15 9-4.5 1.5L9 15l4.5-1.5L15 9Z" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
    </svg>
  )
}

export function IconPerson({ className = 'icon icon-sm' }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="8" r="3.5" stroke="currentColor" strokeWidth="1.8" />
      <path d="M4.5 20c1.3-3.6 4.3-5.5 7.5-5.5s6.2 1.9 7.5 5.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  )
}

// Literal shoe profile, for the handful of Profile-screen spots (stat
// pill, hero meta row) that talk about steps at a size big enough for a
// shoe to read clearly - IconFootsteps' stairs glyph stays put everywhere
// it's already relied on (trip cards etc.) since that one's tuned for
// much smaller inline text instead.
export function IconShoe({ className = 'icon icon-sm' }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M3 17.5h17a1 1 0 0 0 1-1v-1.2c0-.6-.4-1.1-1-1.3l-2.6-.8a2 2 0 0 1-1.1-.9l-1.1-1.8a2.5 2.5 0 0 0-2.5-1.2L6 10.6a3 3 0 0 0-1.8 1L3 13Z"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
      <path d="M8.3 11.9l1.1 1.5M10.6 10.8l1.1 1.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  )
}

export function IconMedal({ className = 'icon icon-sm' }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M8 3 6 9M16 3l2 6" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="12" cy="14" r="6" stroke="currentColor" strokeWidth="1.7" />
      <path d="M12 11.2 13 13.3 15.3 13.6 13.6 15.2 14 17.5 12 16.3 10 17.5 10.4 15.2 8.7 13.6 11 13.3Z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
    </svg>
  )
}

export function IconMap({ className = 'icon icon-sm' }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M3 7 9 4 15 7 21 4 21 18 15 21 9 18 3 21Z" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" strokeLinecap="round" />
      <path d="M9 4v14M15 7v14" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" strokeLinecap="round" />
      <circle cx="12" cy="12" r="1.2" fill="currentColor" />
    </svg>
  )
}

export function IconPencil({ className = 'icon icon-sm' }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M15.2 4.3 19.7 8.8 8.5 20 4 20.5 4.5 16Z" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" strokeLinecap="round" />
      <path d="M13 6.5 17.5 11" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  )
}

export function IconLock({ className = 'icon icon-sm' }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="5.5" y="11" width="13" height="9" rx="2" stroke="currentColor" strokeWidth="1.8" />
      <path d="M8 11V8a4 4 0 0 1 8 0v3" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  )
}

// Sidebar "Settings" entry - a ring (the gear's hub) with eight stubby
// teeth, thicker than the hub's own stroke so it reads as a gear rather
// than the theme toggle's sun (same radiating-line idea, different
// weight on purpose).
export function IconGear({ className = 'icon icon-sm' }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="3.1" stroke="currentColor" strokeWidth="1.8" />
      <path
        d="M12 3.3v2.3M12 18.4v2.3M20.7 12h-2.3M5.6 12H3.3M18.1 5.9l-1.6 1.6M7.5 16.5l-1.6 1.6M18.1 18.1l-1.6-1.6M7.5 7.5 5.9 5.9"
        stroke="currentColor"
        strokeWidth="2.6"
        strokeLinecap="round"
      />
    </svg>
  )
}

// Sidebar "Support" entry - a life buoy, the plainest unambiguous "help"
// glyph in this stroke language.
export function IconLifeBuoy({ className = 'icon icon-sm' }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="8.5" stroke="currentColor" strokeWidth="1.8" />
      <circle cx="12" cy="12" r="3.3" stroke="currentColor" strokeWidth="1.8" />
      <path
        d="m6 6 3.3 3.3M18 6l-3.3 3.3M6 18l3.3-3.3M18 18l-3.3-3.3"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </svg>
  )
}

// The Google Health connection pill's own icon (Topbar.tsx/Sidebar.tsx) -
// a location pin broadcasting a live signal, reading as "connection" (not
// just "place") even before the pill's own text/color make the state
// explicit.
export function IconConnection({ className = 'icon icon-sm' }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M12 21s6-6.4 6-11.2A6 6 0 1 0 6 9.8C6 14.6 12 21 12 21Z" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
      <circle cx="12" cy="9.6" r="1.6" fill="currentColor" />
      <path d="M3.5 10.5a9 9 0 0 1 1.3-4M20.5 10.5a9 9 0 0 0-1.3-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  )
}

// Connected state's check, swapped in for IconConnection above rather
// than a literal "✓" character (keeps this consistent with every other
// status/label glyph in the app being a real SVG, not a unicode symbol).
export function IconCheck({ className = 'icon icon-sm' }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="m5 12.5 4.5 4.5L19 7.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

// The brand mark - a single footprint inside a ring, same "a step is the
// unit this whole app is built on" idea as IconFootsteps/IconShoe
// elsewhere, just distilled into something legible at logo size.
// MarketingHeader.tsx's replacement for the literal 🌍 emoji that used
// to sit there (every other glyph in this app is a real SVG, not a
// unicode symbol - that one was the last holdout).
export function IconFootprintMark({ className = 'icon icon-sm' }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="9.5" stroke="currentColor" strokeWidth="1.5" />
      <path
        d="M10.4 8.3c.3-1 .2-2.3-1-2.3-1.3 0-1.7 1.6-1.5 3 .1 1 .6 1.6.5 2.6-.1 1.4-1 2-1 3.6 0 1.6 1 2.8 2.3 2.8 1.2 0 1.8-.9 1.9-2.1.1-1.5-.5-2-.6-3.3-.1-1.1.2-1.6.4-2.5Z"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinejoin="round"
      />
      <circle cx="8.3" cy="6.6" r="0.9" fill="currentColor" />
      <circle cx="9.9" cy="5.9" r="0.75" fill="currentColor" />
      <circle cx="11.2" cy="6.4" r="0.6" fill="currentColor" />
    </svg>
  )
}

// A plain X - AuthModal.tsx's close button, same "real SVG, not a
// unicode/HTML symbol" rule as every other glyph in this app.
export function IconClose({ className = 'icon icon-sm' }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="m6 6 12 12M18 6 6 18" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  )
}
