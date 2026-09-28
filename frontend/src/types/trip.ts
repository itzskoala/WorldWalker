// Mirrors the shapes core/facade.py builds for the frontend:
// _build_map_state() (TripMapState), _trip_summary() (TripSummary), and
// _checkpoint_state() (Checkpoint) - see app.py's /api/journey/* routes.

export interface Coordinates {
  lat: number
  lng: number
}

export type TripStatus = 'active' | 'paused' | 'completed'

// "pending" the instant a checkpoint's location is known - before its AI
// description exists yet (core/facade.py's generate_checkpoints_for_trip())
// - "ready" once real text exists (or the plain fallback line, on a
// model/network failure). Lets the map show a checkpoint's pin right away
// with a "generating…" marker instead of waiting for its description.
export type CheckpointDescriptionStatus = 'pending' | 'ready'

export interface Checkpoint {
  checkpoint_number: number
  name: string
  coords: Coordinates
  distance_from_start_m: number
  description: string
  description_status: CheckpointDescriptionStatus
  hit: boolean
  hit_at: string | null
}

/** The full map-ready shape - GET /api/journey/state and (on success)
 * POST /api/journey/start. */
export interface TripMapState {
  trip_id: string
  status: TripStatus
  from_place: string
  to_place: string
  round_trip: boolean
  start: Coordinates
  end: Coordinates
  route_geometry: Coordinates[]
  walked_geometry: Coordinates[]
  current_position: Coordinates
  total_distance_m: number
  distance_walked_m: number
  distance_remaining_m: number
  miles_walked: number
  miles_remaining: number
  percent_complete: number
  estimated_days_remaining: number | null
  total_steps: number
  today_steps: number
  started_at: string
  elapsed_seconds: number
  // False the instant start_journey() returns (checkpoints is still [] at
  // that point) - true once generate_checkpoints_for_trip()'s background
  // job has found every checkpoint along the route. TripDetailPage.tsx
  // only opens GET /api/journey/{trip_id}/events while this is false.
  checkpoints_ready: boolean
  checkpoints: Checkpoint[]
}

/** GET /api/journey/list's per-card shape - cheaper than TripMapState,
 * no checkpoints/current-position. */
export interface TripSummary {
  trip_id: string
  status: TripStatus
  from_place: string
  to_place: string
  round_trip: boolean
  total_distance_m: number
  distance_walked_m: number
  miles_total: number
  miles_walked: number
  percent_complete: number
  started_at: string
  thumbnail_route: Coordinates[]
}

/** POST /api/journey/start - `coming_soon: true` means the geocode/route/
 * checkpoint pipeline failed server-side (app.py fails soft, not a 500);
 * there is no trip to show, just app.js's "coming soon" messaging. */
export type JourneyStartResponse = { coming_soon: true } | ({ coming_soon: false } & TripMapState)

export interface PlaceSuggestion {
  value: string
  primary: string
  secondary: string
}

/** AppShell's one piece of Trip Detail state - a React port of trip.js's
 * showLoading()/show()/showError()/openTrip() state machine. `sessionId`
 * is used as a React `key` so starting a new walk or opening a different
 * trip always gets a genuinely fresh TripDetailPage mount (and therefore
 * a fresh map instance) - trip.js's own rule, enforced there by hand with
 * a requestId counter; here it falls out of React's own lifecycle. */
export interface TripSession {
  sessionId: number
  tripId: string | null
  fromPlace: string
  toPlace: string
  status: 'loading' | 'error' | 'ready'
  errorMessage?: string
  initialState?: TripMapState
}
