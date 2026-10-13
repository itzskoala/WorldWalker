// Square route-sparkline thumbnail for a trip row (TripRow.tsx) - draws
// trip.thumbnail_route (a downsampled lat/lng polyline, see core/
// facade.py's _thumbnail_route()) scaled to fit a small square. There's
// no photo asset per trip server-side, so this - not a destination photo
// - is the thumbnail everywhere a trip needs one.

import type { Coordinates } from '../../types/trip'

export function TripThumb({ routePoints }: { routePoints: Coordinates[] }) {
  if (!routePoints || routePoints.length < 2) {
    return (
      <div className="walks-thumb">
        <svg viewBox="0 0 52 52" />
      </div>
    )
  }

  const lats = routePoints.map((p) => p.lat)
  const lngs = routePoints.map((p) => p.lng)
  const minLat = Math.min(...lats)
  const maxLat = Math.max(...lats)
  const minLng = Math.min(...lngs)
  const maxLng = Math.max(...lngs)
  const spanLat = maxLat - minLat || 1
  const spanLng = maxLng - minLng || 1
  const pad = 8
  const size = 52
  const points = routePoints
    .map((p) => {
      const x = pad + ((p.lng - minLng) / spanLng) * (size - pad * 2)
      const y = pad + (1 - (p.lat - minLat) / spanLat) * (size - pad * 2)
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')

  return (
    <div className="walks-thumb">
      <svg viewBox={`0 0 ${size} ${size}`}>
        <polyline points={points} fill="none" stroke="var(--green)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </div>
  )
}
