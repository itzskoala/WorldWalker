import { useEffect, useRef } from 'react'
import { createTripMap } from '../components/tripMap'
import type { TripMapState } from '../types/trip'

const FAKE_STATE: TripMapState = {
  trip_id: 'test',
  status: 'active',
  from_place: 'San Francisco',
  to_place: 'Oakland',
  start: { lat: 37.7749, lng: -122.4194 },
  end: { lat: 37.8044, lng: -122.2712 },
  route_geometry: [
    { lat: 37.7749, lng: -122.4194 },
    { lat: 37.79, lng: -122.38 },
    { lat: 37.8044, lng: -122.2712 },
  ],
  walked_geometry: [
    { lat: 37.7749, lng: -122.4194 },
    { lat: 37.79, lng: -122.38 },
  ],
  current_position: { lat: 37.79, lng: -122.38 },
  total_distance_m: 15000,
  distance_walked_m: 7000,
  distance_remaining_m: 8000,
  miles_walked: 4.3,
  miles_remaining: 5,
  percent_complete: 46,
  estimated_days_remaining: 2,
  total_steps: 9000,
  today_steps: 3000,
  started_at: new Date().toISOString(),
  elapsed_seconds: 3600,
  checkpoints_ready: false,
  total_checkpoints: 0,
  discovered_checkpoints: 0,
  checkpoints: [],
}

export function MapTestPage() {
  const ref = useRef<ReturnType<typeof createTripMap> | null>(null)

  useEffect(() => {
    const controller = createTripMap('trip-map')
    ref.current = controller
    controller.mount()
    controller.renderInitial(FAKE_STATE)
    return () => controller.destroy()
  }, [])

  return (
    <section className="trip-view" style={{ height: '100vh' }}>
      <div className="trip-map-full" id="trip-map" />
    </section>
  )
}
