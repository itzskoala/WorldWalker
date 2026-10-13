// Standalone filter pills above the All Trips list (HomePage.tsx) - each
// pill is independently bordered, unlike .trip-toggle/.trip-pill's single
// segmented-control shell elsewhere in this app (CreatePage's round-trip
// toggle), since the design calls for them reading as separate chips in
// a row rather than one grouped control.
//
// One pill per real TripSummary.status (active/paused/completed), plus
// Favorites - no separate "Saved" pill: every trip here has already been
// started (there's no "bookmarked, not yet walked" concept in this data
// model), so it would have nothing of its own to filter to. Favorites
// already covers "the ones I've bookmarked."

export type WalksFilter = 'all' | 'active' | 'paused' | 'completed' | 'favorites'

const FILTERS: { value: WalksFilter; label: string }[] = [
  { value: 'all', label: 'All Trips' },
  { value: 'active', label: 'In Progress' },
  { value: 'paused', label: 'Paused' },
  { value: 'completed', label: 'Completed' },
  { value: 'favorites', label: 'Favorites' },
]

interface FilterPillBarProps {
  active: WalksFilter
  onChange: (filter: WalksFilter) => void
}

export function FilterPillBar({ active, onChange }: FilterPillBarProps) {
  return (
    <div className="walks-filter-row" role="group" aria-label="Filter trips">
      {FILTERS.map(({ value, label }) => (
        <button
          key={value}
          type="button"
          className={`walks-filter-pill${active === value ? ' is-active' : ''}`}
          aria-pressed={active === value}
          onClick={() => onChange(value)}
        >
          {label}
        </button>
      ))}
    </div>
  )
}
