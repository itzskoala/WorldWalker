// Port of web/static/js/app.js's PlaceField class - a text input with a
// debounced /api/places/search dropdown, keyboard nav, and a clear
// button. Controlled from the outside (value/onChange) so CreatePage can
// read both fields for "Start Walking" and swap them.

import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import type { PlaceSuggestion, ResolvedPlace } from '../types/trip'

const DEBOUNCE_MS = 220

function highlightParts(text: string, query: string): [string, string, string] {
  const q = query.trim().toLowerCase()
  if (!q) return [text, '', '']
  const idx = text.toLowerCase().indexOf(q)
  if (idx === -1) return [text, '', '']
  return [text.slice(0, idx), text.slice(idx, idx + query.trim().length), text.slice(idx + query.trim().length)]
}

interface PlaceAutocompleteProps {
  id: string
  label: string
  placeholder: string
  value: string
  onChange: (value: string) => void
  // Fires when a suggestion (or "Use current location") resolves to real
  // coordinates - distinct from onChange, which fires on every keystroke
  // and carries no coordinates. The parent owns turning free-typed text
  // back into an unresolved state.
  onSelect: (place: ResolvedPlace) => void
  pinColor: 'green' | 'red'
  currentLocationButton?: boolean
  // Lets the parent grow this field's column while it's focused, so a
  // long query stays fully visible - see CreatePage.tsx's `.fields-row`.
  onActiveChange?: (active: boolean) => void
  // Fires whenever this field is actively trying to resolve something -
  // a debounced /api/places/search request in flight, or "Use current
  // location" mid-lookup - so the parent can hold Start Walking disabled
  // through that window even though a *previous* resolution technically
  // still sits in state (see useCurrentLocation() below).
  onResolvingChange?: (resolving: boolean) => void
  // Whether `value` is currently a resolved place (the parent's
  // fromLocation/toLocation is non-null) rather than free-typed text.
  // While true, this never searches, no matter how `value` changes - a
  // selection, "Use current location", or swap() all just update `value`
  // from the parent's side, which used to be indistinguishable here from
  // the user typing and re-triggered a search for the exact text just
  // resolved, reopening the dropdown on its own result. Search resumes
  // the instant this goes false again (the parent already does that on
  // any hand-edit - see CreatePage.tsx's setFrom/setTo).
  resolved: boolean
}

export function PlaceAutocomplete({ id, label, placeholder, value, onChange, onSelect, pinColor, currentLocationButton, onActiveChange, onResolvingChange, resolved }: PlaceAutocompleteProps) {
  const [results, setResults] = useState<PlaceSuggestion[]>([])
  const [open, setOpen] = useState(false)
  const [activeIndex, setActiveIndex] = useState(-1)
  const [searching, setSearching] = useState(false)
  const [locating, setLocating] = useState(false)
  const fieldRef = useRef<HTMLDivElement>(null)
  const listRef = useRef<HTMLUListElement>(null)
  // Enter pressed while a search for the current text is still in
  // flight - there's nothing to select or clear yet, so this defers that
  // intent to the moment the search actually settles, rather than
  // silently dropping the keypress (see onKeyDown and the search effect
  // below). Reset at the top of every new search - a keystroke made
  // after pressing Enter invalidates whatever Enter meant for the
  // now-stale in-flight request.
  const pendingEnterRef = useRef(false)

  // One combined "still working on it" signal out to the parent -
  // Start Walking cares that *something* is unresolved, not which of the
  // two async sources caused it.
  useEffect(() => {
    onResolvingChange?.(searching || locating)
  }, [searching, locating, onResolvingChange])

  // Debounced search, cancelling a slower now-stale request the same way
  // PlaceField.search() did with an AbortController. Fires from the
  // first character - no minimum length gate - so typing "F" starts
  // searching immediately instead of waiting for a second keystroke.
  // Never fires while `resolved` - see that prop's doc comment above for
  // exactly what this prevents.
  useEffect(() => {
    pendingEnterRef.current = false // a fresh keystroke cancels any earlier queued Enter
    const query = value.trim()
    if (!query || resolved) {
      setResults([])
      setOpen(false)
      setSearching(false)
      return
    }

    const controller = new AbortController()
    setSearching(true)
    const timer = setTimeout(async () => {
      let finalResults: PlaceSuggestion[] = []
      try {
        const res = await fetch(`/api/places/search?q=${encodeURIComponent(query)}`, { signal: controller.signal })
        if (res.ok) {
          const data = (await res.json()) as { results: PlaceSuggestion[] }
          finalResults = data.results
          setResults(finalResults)
          setActiveIndex(-1)
          setOpen(finalResults.length > 0)
        }
      } catch (err) {
        if ((err as Error).name !== 'AbortError') setResults([])
      } finally {
        if (!controller.signal.aborted) {
          setSearching(false)
          if (pendingEnterRef.current) {
            pendingEnterRef.current = false
            if (finalResults.length > 0) {
              const top = finalResults[0]
              onSelect({ label: top.value, lat: top.lat, lng: top.lng })
              setOpen(false)
            } else {
              onChange('')
            }
          }
        }
      }
    }, DEBOUNCE_MS)

    return () => {
      controller.abort()
      clearTimeout(timer)
    }
  }, [value, resolved])

  // Close the dropdown on an outside click - PlaceField's own
  // document-level listener.
  useEffect(() => {
    function onDocClick(e: MouseEvent) {
      if (fieldRef.current && !fieldRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('click', onDocClick)
    return () => document.removeEventListener('click', onDocClick)
  }, [])

  function select(index: number) {
    const choice = results[index]
    if (!choice) return
    onSelect({ label: choice.value, lat: choice.lat, lng: choice.lng })
    setOpen(false)
  }

  // Typed a real, legit place and clicked away instead of clicking the
  // suggestion - commits to the top current match automatically (same as
  // Enter already does), so leaving the field isn't required to still
  // count as choosing it. Does nothing if nothing actually matches: per
  // an earlier explicit decision, only a failed *Enter* clears a field -
  // blurring away from genuinely unmatched text just leaves it as free
  // text, unresolved (Start Walking already stays disabled for that).
  function resolveToTopMatchOnBlur() {
    if (resolved || !value.trim()) return
    if (searching) {
      // The debounced search for this exact text hasn't answered yet -
      // queue it, same as Enter does; the search effect below resolves
      // this the moment it settles.
      pendingEnterRef.current = true
      return
    }
    if (results.length > 0) select(activeIndex >= 0 ? activeIndex : 0)
  }

  function onKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (!open || !results.length) {
      if (e.key === 'Escape') {
        setOpen(false)
      } else if (e.key === 'Enter' && !resolved && value.trim()) {
        e.preventDefault()
        if (searching) {
          // The debounced search for this exact text hasn't answered yet
          // - nothing to select or clear until it does. Queue the intent
          // instead of dropping it; the search effect resolves this the
          // moment it settles.
          pendingEnterRef.current = true
        } else {
          // Settled with nothing: neither the local index nor Nominatim
          // (see /api/places/search) matched this query. Clear rather
          // than leaving unresolvable text sitting in the field looking
          // like a real answer. Guarded on !resolved so this can't fire
          // on an already-resolved field (results is also empty right
          // after a real selection, by design - see the search effect).
          onChange('')
        }
      }
      return
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActiveIndex((i) => Math.min(i + 1, results.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActiveIndex((i) => Math.max(i - 1, 0))
    } else if (e.key === 'Enter') {
      // Resolves the top match even if the user never arrow-key'd to it -
      // typing a full query and hitting Enter should commit to whatever
      // it already found (local index or Nominatim, whichever
      // /api/places/search answered from) exactly like clicking the first
      // row would. Only reachable when results.length > 0 (the early
      // return above), so results[0] always exists here.
      e.preventDefault()
      select(activeIndex >= 0 ? activeIndex : 0)
    } else if (e.key === 'Escape') {
      setOpen(false)
    }
  }

  useEffect(() => {
    if (activeIndex < 0) return
    listRef.current?.querySelectorAll('.suggestion')[activeIndex]?.scrollIntoView({ block: 'nearest' })
  }, [activeIndex])

  function useCurrentLocation() {
    if (!navigator.geolocation) {
      console.warn('Geolocation unsupported in this browser.')
      return
    }
    setLocating(true)
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        try {
          const { latitude, longitude } = pos.coords
          const res = await fetch(`/api/places/reverse?lat=${latitude}&lng=${longitude}`)
          if (!res.ok) throw new Error(`HTTP ${res.status}`)
          const data = (await res.json()) as { place: string }
          // The browser's own coordinates are more precise than
          // re-geocoding the reverse-geocoded place name would be.
          onSelect({ label: data.place, lat: latitude, lng: longitude })
        } catch (err) {
          console.warn('Reverse geocode failed:', err)
        } finally {
          setLocating(false)
        }
      },
      (err) => {
        setLocating(false)
        console.warn('Geolocation failed:', err.message || err)
      },
      { timeout: 8000 },
    )
  }

  return (
    <div className="field" id={`field-${id}`} ref={fieldRef}>
      <label className="field-label" htmlFor={`input-${id}`}>
        {label}
      </label>
      <div className="field-input">
        <svg className={`icon icon-pin icon-${pinColor}`} viewBox="0 0 24 24" fill="none">
          <path d="M12 22s7-7.58 7-13A7 7 0 0 0 5 9c0 5.42 7 13 7 13Z" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
          <circle cx="12" cy="9" r="2.5" stroke="currentColor" strokeWidth="1.8" />
        </svg>
        <input
          id={`input-${id}`}
          type="text"
          autoComplete="off"
          placeholder={placeholder}
          role="combobox"
          aria-expanded={open}
          aria-controls={`list-${id}`}
          aria-autocomplete="list"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={onKeyDown}
          onFocus={() => {
            onActiveChange?.(true)
            if (results.length && value.trim()) setOpen(true)
          }}
          onBlur={(e) => {
            onActiveChange?.(false)
            // Don't resolve out from under this field's own clear/
            // current-location buttons - each already has its own, more
            // specific handling (clearing, or a real geolocation lookup)
            // that would otherwise be briefly overwritten by whatever
            // this resolves to.
            if (fieldRef.current?.contains(e.relatedTarget as Node | null)) return
            resolveToTopMatchOnBlur()
          }}
        />
        {value && (
          <button type="button" className="field-clear" aria-label={`Clear ${label.toLowerCase()}`} onClick={() => onChange('')}>
            &times;
          </button>
        )}
      </div>

      <ul className="suggestions" id={`list-${id}`} role="listbox" hidden={!open} ref={listRef}>
        {results.map((r, i) => {
          const [before, match, after] = highlightParts(r.primary, value)
          return (
            <li
              key={r.value}
              className={`suggestion${i === activeIndex ? ' is-active' : ''}`}
              role="option"
              aria-selected={i === activeIndex}
              onMouseDown={(e) => {
                e.preventDefault()
                select(i)
              }}
            >
              <svg className="icon" viewBox="0 0 24 24" fill="none">
                <path d="M12 22s7-7.58 7-13A7 7 0 0 0 5 9c0 5.42 7 13 7 13Z" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
                <circle cx="12" cy="9" r="2.5" stroke="currentColor" strokeWidth="1.8" />
              </svg>
              <span className="suggestion-text">
                <span className="suggestion-primary">
                  {before}
                  {match && <mark>{match}</mark>}
                  {after}
                </span>
                {r.secondary && <span className="suggestion-secondary">{r.secondary}</span>}
              </span>
            </li>
          )
        })}
      </ul>

      {currentLocationButton && (
        <button type="button" className={`current-loc-btn${locating ? ' is-loading' : ''}`} onClick={useCurrentLocation}>
          <svg className="icon" viewBox="0 0 24 24" fill="none">
            <circle cx="12" cy="12" r="3" stroke="currentColor" strokeWidth="1.8" />
            <path d="M12 2v3M12 19v3M2 12h3M19 12h3" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
          </svg>
          Use current location
        </button>
      )}
    </div>
  )
}
