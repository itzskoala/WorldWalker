// Mirrors the shapes core/facade.py builds for the frontend:
// _build_map_state() (TripMapState), _trip_summary() (TripSummary), and
// _checkpoint_state() (Checkpoint) - see app.py's /api/journey/* routes.

export interface Coordinates {
  lat: number
  lng: number
}

export type TripStatus = 'active' | 'paused' | 'completed'

// "pending" the instant a checkpoint's position exists - name/description
// both still blank - "processing" while a background job is actively
// resolving them, "ready" once real text exists for both (or the plain
// fallback description, on a model/network failure). Every checkpoint's
// *position* exists from the moment a trip is created now (core/facade.py's
// start_journey()); this only ever describes how far its name/description
// resolution has gotten - treat "processing" the same as "pending" (both
// mean "still generating…") unless you specifically need to tell them
// apart.
export type CheckpointDescriptionStatus = 'pending' | 'processing' | 'ready'

export interface Checkpoint {
  checkpoint_number: number
  name: string
  coords: Coordinates
  distance_from_start_m: number
  description: string
  description_status: CheckpointDescriptionStatus
  // Proximity-revealed: true once the walker has come within this trip's
  // own randomized reveal radius of this checkpoint - set once, never
  // cleared, independent of description_status (a checkpoint can reveal
  // itself before its name/description are ready). The map only ever
  // renders a marker for a checkpoint where this is true.
  revealed: boolean
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
  // True only once the trip itself is finished - metadata/reveal events
  // keep arriving for an active trip's whole duration now (checkpoints
  // resolve/reveal lazily, as the walker approaches each one, not all at
  // once early on). TripDetailPage.tsx only opens GET /api/journey/
  // {trip_id}/events while this is false, since a finished trip has
  // nothing left to stream.
  checkpoints_ready: boolean
  // Every checkpoint's position for the whole route, generated up front
  // - this never changes for the life of the trip.
  total_checkpoints: number
  // How many checkpoints the walker has actually uncovered so far
  // (checkpoints.filter(c => c.revealed).length, computed server-side) -
  // what the map-reveal progress pill shows. Deliberately not the same
  // as "how many have description_status === 'ready'": a checkpoint can
  // be revealed well before its metadata finishes resolving.
  discovered_checkpoints: number
  checkpoints: Checkpoint[]
}

/** GET /api/journey/list's per-card shape - cheaper than TripMapState: no
 * full route rebuild/current-position, but still everything the My Walks
 * dashboard needs (frontend/src/pages/HomePage.tsx, components/walks/),
 * including total_steps and current_checkpoint_name - HomePage.tsx used
 * to fetch a full TripMapState per active trip just for those two
 * fields; core/facade.py's list_trips() computes them directly now, so
 * that extra per-trip fetch is gone. */
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
  total_steps: number
  current_checkpoint_name: string | null
}

/** POST /api/journey/start - `coming_soon: true` means the geocode/route/
 * checkpoint pipeline failed server-side (app.py fails soft, not a 500);
 * there is no trip to show, just app.js's "coming soon" messaging. */
export type JourneyStartResponse = { coming_soon: true } | ({ coming_soon: false } & TripMapState)

export interface PlaceSuggestion extends Coordinates {
  value: string
  primary: string
  secondary: string
}

/** A location that's been resolved to real coordinates - by picking an
 * autocomplete suggestion, or by "Use current location" - as opposed to
 * free-typed text nothing has matched yet. */
export interface ResolvedPlace extends Coordinates {
  label: string
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
