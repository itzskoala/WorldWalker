// Port of web/static/js/app.js's PlaceField class - a text input with a
// debounced /api/places/search dropdown, keyboard nav, and a clear
// button. Controlled from the outside (value/onChange) so CreatePage can
// read both fields for "Start Walking" and swap them.

import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import type { PlaceSuggestion } from '../types/trip'

const DEBOUNCE_MS = 220
const MIN_CHARS = 2

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
  pinColor: 'green' | 'red'
  currentLocationButton?: boolean
}

export function PlaceAutocomplete({ id, label, placeholder, value, onChange, pinColor, currentLocationButton }: PlaceAutocompleteProps) {
  const [results, setResults] = useState<PlaceSuggestion[]>([])
  const [open, setOpen] = useState(false)
  const [activeIndex, setActiveIndex] = useState(-1)
  const [locating, setLocating] = useState(false)
  const fieldRef = useRef<HTMLDivElement>(null)
  const listRef = useRef<HTMLUListElement>(null)

  // Debounced search, cancelling a slower now-stale request the same way
  // PlaceField.search() did with an AbortController.
  useEffect(() => {
    const query = value.trim()
    if (query.length < MIN_CHARS) {
      setResults([])
      setOpen(false)
      return
    }

    const controller = new AbortController()
    const timer = setTimeout(async () => {
      try {
        const res = await fetch(`/api/places/search?q=${encodeURIComponent(query)}`, { signal: controller.signal })
        if (!res.ok) return
        const data = (await res.json()) as { results: PlaceSuggestion[] }
        setResults(data.results)
        setActiveIndex(-1)
        setOpen(data.results.length > 0)
      } catch (err) {
        if ((err as Error).name !== 'AbortError') setResults([])
      }
    }, DEBOUNCE_MS)

    return () => {
      controller.abort()
      clearTimeout(timer)
    }
  }, [value])

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
    onChange(choice.value)
    setOpen(false)
  }

  function onKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (!open || !results.length) {
      if (e.key === 'Escape') setOpen(false)
      return
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActiveIndex((i) => Math.min(i + 1, results.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActiveIndex((i) => Math.max(i - 1, 0))
    } else if (e.key === 'Enter') {
      if (activeIndex >= 0) {
        e.preventDefault()
        select(activeIndex)
      }
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
          onChange(data.place)
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
            if (results.length && value.trim().length >= MIN_CHARS) setOpen(true)
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
