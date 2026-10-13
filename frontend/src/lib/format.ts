// Shared number/date formatting for the My Walks dashboard
// (pages/HomePage.tsx, components/walks/*).

const METERS_PER_MILE = 1609.344

// TripSummary carries distance and step count per trip, but never a
// logged duration - there's no "time walking" field to sum (see
// types/trip.ts; only the live Trip Detail map's TripMapState has
// elapsed_seconds, and that's wall-clock-since-start, not fetchable per
// trip here without reintroducing the N+1 fetch core/facade.py's
// list_trips() was written to avoid). Every "time" shown on this
// dashboard is instead estimated from distance at an average walking
// pace - swap this for a real per-trip duration if the backend ever
// tracks one.
const WALKING_MPH = 3

export function metersToMiles(meters: number): number {
  return meters / METERS_PER_MILE
}

export function formatMiles(meters: number): string {
  return `${metersToMiles(meters).toFixed(1)} mi`
}

// The All Trips "Trip Overview Card" spec calls out km specifically
// (current/total mileage, e.g. "5.2 km / 12.4 km") - everywhere else on
// this dashboard (the stats row, TripRow's compact rows) stays in miles,
// matching TripSummary's own miles_total/miles_walked fields, so this is
// deliberately scoped to that one card rather than a unit-wide switch.
export function formatKm(meters: number): string {
  return `${(meters / 1000).toFixed(1)} km`
}

export function estimatedDurationSeconds(meters: number): number {
  return (metersToMiles(meters) / WALKING_MPH) * 3600
}

export function formatDuration(seconds: number): string {
  const totalMinutes = Math.max(1, Math.round(seconds / 60))
  const hours = Math.floor(totalMinutes / 60)
  const minutes = totalMinutes % 60
  if (hours === 0) return `${minutes}m`
  if (minutes === 0) return `${hours}h`
  return `${hours}h ${minutes}m`
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}
