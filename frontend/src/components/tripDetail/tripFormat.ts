const METERS_PER_MILE = 1609.344
const METERS_PER_KM = 1000
const UNITS_STORAGE_KEY = 'ww-trip-units'

export type DistanceUnit = 'mi' | 'km'

export function readSavedUnit(): DistanceUnit {
  try {
    return localStorage.getItem(UNITS_STORAGE_KEY) === 'km' ? 'km' : 'mi'
  } catch {
    return 'mi'
  }
}

function metersToUnit(meters: number, unit: DistanceUnit): number {
  return unit === 'km' ? meters / METERS_PER_KM : meters / METERS_PER_MILE
}

export function formatDistance(meters: number, unit: DistanceUnit, decimals = 1): string {
  return `${metersToUnit(meters, unit).toFixed(decimals)} ${unit}`
}

// elapsed_seconds is already "time actually walking" - core/facade.py's
// _elapsed_seconds excludes paused time.
export function formatElapsedDuration(totalSeconds: number): string {
  const totalMinutes = Math.max(0, Math.round(totalSeconds / 60))
  const days = Math.floor(totalMinutes / 1440)
  const hours = Math.floor((totalMinutes % 1440) / 60)
  const minutes = totalMinutes % 60

  if (days > 0) return `${days}d ${hours}h`
  if (hours > 0) return `${hours}h ${minutes}m`
  return `${minutes}m`
}
