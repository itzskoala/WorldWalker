// The React seam for src/components/tripMap.ts - mounts the map once
// when the container is ready, tears it down on unmount/containerId
// change, and exposes renderInitial/update for the owning page to call
// as trip state arrives. Deliberately thin: no map logic lives here, only
// the mount/unmount lifecycle - see tripMap.ts's own header comment for
// why the map component itself stays a plain (non-React) module.

import { useEffect, useRef, useState } from 'react'
import { createTripMap, type TripMapController } from '../components/tripMap'

interface UseTripMapOptions {
  containerId: string
  onReady?: () => void
  onError?: (err: Error) => void
}

export function useTripMap({ containerId, onReady, onError }: UseTripMapOptions) {
  const controllerRef = useRef<TripMapController | null>(null)
  const [mountToken, setMountToken] = useState(0)

  // A fresh instance every time the caller wants one (trip.js's own rule:
  // "each trip gets its own fresh instance") - callers force this by
  // changing containerId's key or calling remount().
  useEffect(() => {
    const controller = createTripMap(containerId, { onReady, onError })
    controllerRef.current = controller
    controller.mount()

    return () => {
      controller.destroy()
      controllerRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [containerId, mountToken])

  function remount() {
    setMountToken((t) => t + 1)
  }

  return { controllerRef, remount }
}
