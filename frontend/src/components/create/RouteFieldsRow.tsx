import { PlaceAutocomplete } from '../PlaceAutocomplete'
import type { ResolvedPlace } from '../../types/trip'

interface RouteFieldsRowProps {
  activeField: 'from' | 'to' | null
  onActiveFieldChange: (field: 'from' | 'to' | null) => void
  from: string
  onFromChange: (value: string) => void
  onFromSelect: (place: ResolvedPlace) => void
  onFromResolvingChange: (resolving: boolean) => void
  fromResolved: boolean
  to: string
  onToChange: (value: string) => void
  onToSelect: (place: ResolvedPlace) => void
  onToResolvingChange: (resolving: boolean) => void
  toResolved: boolean
  swapping: boolean
  onSwap: () => void
}

export function RouteFieldsRow({
  activeField,
  onActiveFieldChange,
  from,
  onFromChange,
  onFromSelect,
  onFromResolvingChange,
  fromResolved,
  to,
  onToChange,
  onToSelect,
  onToResolvingChange,
  toResolved,
  swapping,
  onSwap,
}: RouteFieldsRowProps) {
  return (
    <div className="fields-row" data-active={activeField ?? undefined}>
      <PlaceAutocomplete
        id="from"
        label="Where from?"
        placeholder="City, State, or Address"
        pinColor="green"
        value={from}
        onChange={onFromChange}
        onSelect={onFromSelect}
        onActiveChange={(active) => onActiveFieldChange(active ? 'from' : null)}
        onResolvingChange={onFromResolvingChange}
        resolved={fromResolved}
        currentLocationButton
      />

      <button type="button" className={`swap-btn${swapping ? ' is-spinning' : ''}`} aria-label="Swap starting point and destination" onClick={onSwap}>
        <svg className="icon" viewBox="0 0 24 24" fill="none">
          <path d="M7 7h12m0 0-4-4m4 4-4 4M17 17H5m0 0 4 4m-4-4 4-4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>

      <PlaceAutocomplete
        id="to"
        label="Where to?"
        placeholder="Oh, the places you'll go!"
        pinColor="red"
        value={to}
        onChange={onToChange}
        onSelect={onToSelect}
        onActiveChange={(active) => onActiveFieldChange(active ? 'to' : null)}
        onResolvingChange={onToResolvingChange}
        resolved={toResolved}
      />
    </div>
  )
}
