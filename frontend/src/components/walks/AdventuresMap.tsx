// "Your Adventures" card (HomePage.tsx) - a stylized, schematic world
// map (same hand-drawn-not-literal register as Sidebar.tsx's
// SidebarMountains or the hero's HeroMountains, not a geographically
// precise basemap) with one node per trip, plotted from that trip's own
// real start coordinates (thumbnail_route[0]) via a plain equirectangular
// projection. Nodes are connected in the order trips were started, by a
// quiet dashed line - the same "quiet route line" register Trip Detail's
// own map already uses for a walked path - with only the most recent
// trip's node picked out in solid teal.

import { useMemo } from 'react'
import type { TripSummary } from '../../types/trip'

const VIEW_W = 1000
const VIEW_H = 460

function project(lat: number, lng: number): { x: number; y: number } {
  return {
    x: ((lng + 180) / 360) * VIEW_W,
    y: ((90 - lat) / 180) * VIEW_H,
  }
}

// Loose, abstract continent silhouettes - purely decorative backdrop,
// not meant to be traced against an atlas.
function WorldBackdrop() {
  return (
    <g className="walks-map-backdrop" fill="currentColor" aria-hidden="true">
      <path d="M90 150 Q60 110 120 90 Q180 70 230 100 Q210 140 240 170 Q190 210 140 190 Q100 190 90 150Z" />
      <path d="M190 230 Q170 280 200 330 Q230 370 260 340 Q280 290 260 250 Q230 210 190 230Z" />
      <path d="M430 110 Q410 80 460 70 Q520 60 540 90 Q560 70 600 80 Q610 110 580 130 Q540 120 520 150 Q470 160 450 140 Q420 140 430 110Z" />
      <path d="M470 190 Q450 240 480 300 Q510 350 540 320 Q560 270 540 220 Q520 180 470 190Z" />
      <path d="M620 110 Q650 80 720 90 Q800 100 850 140 Q880 170 850 200 Q780 220 720 200 Q660 190 630 160 Q610 140 620 110Z" />
      <path d="M760 260 Q800 250 830 280 Q840 310 810 320 Q770 310 760 280Z" />
    </g>
  )
}

interface AdventuresMapProps {
  trips: TripSummary[]
}

export function AdventuresMap({ trips }: AdventuresMapProps) {
  const nodes = useMemo(() => {
    return trips
      .filter((t) => t.thumbnail_route.length > 0)
      .map((t) => {
        const start = t.thumbnail_route[0]
        const { x, y } = project(start.lat, start.lng)
        return { tripId: t.trip_id, label: t.to_place, x, y, startedAt: t.started_at }
      })
      .sort((a, b) => new Date(a.startedAt).getTime() - new Date(b.startedAt).getTime())
  }, [trips])

  const pathD = nodes.length > 1 ? `M ${nodes.map((n) => `${n.x.toFixed(1)} ${n.y.toFixed(1)}`).join(' L ')}` : null
  const mostRecentId = nodes.length > 0 ? nodes[nodes.length - 1].tripId : null

  return (
    <svg className="walks-map" viewBox={`0 0 ${VIEW_W} ${VIEW_H}`} role="img" aria-label="Map of your walking routes around the world">
      <WorldBackdrop />
      {pathD && <path d={pathD} fill="none" stroke="var(--card-border)" strokeWidth="1.5" strokeDasharray="5 5" />}
      {nodes.map((node) => (
        <circle
          key={node.tripId}
          cx={node.x}
          cy={node.y}
          r={node.tripId === mostRecentId ? 7 : 4.5}
          className={node.tripId === mostRecentId ? 'walks-map-node is-recent' : 'walks-map-node'}
        >
          <title>{node.label}</title>
        </circle>
      ))}
    </svg>
  )
}
