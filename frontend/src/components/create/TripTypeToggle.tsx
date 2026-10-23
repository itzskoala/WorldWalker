export type TripType = 'round' | 'one-way'

interface TripTypeToggleProps {
  value: TripType
  onChange: (value: TripType) => void
}

export function TripTypeToggle({ value, onChange }: TripTypeToggleProps) {
  return (
    <div className="trip-toggle" role="radiogroup" aria-label="Trip type">
      <button
        type="button"
        className={`trip-pill${value === 'round' ? ' is-active' : ''}`}
        role="radio"
        aria-checked={value === 'round'}
        onClick={() => onChange('round')}
      >
        Round trip
      </button>
      <button
        type="button"
        className={`trip-pill${value === 'one-way' ? ' is-active' : ''}`}
        role="radio"
        aria-checked={value === 'one-way'}
        onClick={() => onChange('one-way')}
      >
        One way
      </button>
    </div>
  )
}
