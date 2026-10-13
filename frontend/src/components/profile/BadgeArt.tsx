// Illustrated badge artwork for the Badge Case - each one is a small
// self-contained scene inside the same hexagon frame (flat fills, no
// gradients, a thin darker rim for definition and a lighter inset ring
// for an "enamel pin" feel), so an earned badge reads as a memento of a
// specific kind of walk rather than a generic trophy icon repeated four
// times. One component per badge category in src/mock/profileMock.ts.

import type { ReactNode } from 'react'

const HEX = 'M32 3 57 17.5 57 46.5 32 61 7 46.5 7 17.5 Z'
const HEX_INSET = 'M32 6.5 54 19.25 54 44.75 32 57.5 10 44.75 10 19.25 Z'

interface BadgeArtProps {
  className?: string
}

function HexFrame({ fill, rim, children }: { fill: string; rim: string; children: ReactNode }) {
  return (
    <>
      <path d={HEX} fill={fill} stroke={rim} strokeWidth="2" strokeLinejoin="round" />
      <path d={HEX_INSET} fill="none" stroke="#ffffff" strokeOpacity="0.28" strokeWidth="1.4" />
      {children}
    </>
  )
}

export function BadgeFirstSteps({ className = 'badge-art' }: BadgeArtProps) {
  return (
    <svg className={className} viewBox="0 0 64 64" aria-hidden="true">
      <HexFrame fill="var(--blue)" rim="rgba(15,23,42,0.22)">
        <ellipse cx="33" cy="43" rx="6.4" ry="8.4" fill="#ffffff" fillOpacity="0.95" />
        <circle cx="25.5" cy="29" r="2.7" fill="#ffffff" fillOpacity="0.95" />
        <circle cx="30.5" cy="26" r="3.1" fill="#ffffff" fillOpacity="0.95" />
        <circle cx="36" cy="25.5" r="3" fill="#ffffff" fillOpacity="0.95" />
        <circle cx="41" cy="27.5" r="2.6" fill="#ffffff" fillOpacity="0.95" />
        <path d="M46 14.5 47.3 17.7 50.5 19 47.3 20.3 46 23.5 44.7 20.3 41.5 19 44.7 17.7Z" fill="#ffffff" fillOpacity="0.85" />
      </HexFrame>
    </svg>
  )
}

export function BadgeTrailblazer({ className = 'badge-art' }: BadgeArtProps) {
  return (
    <svg className={className} viewBox="0 0 64 64" aria-hidden="true">
      <HexFrame fill="var(--green)" rim="rgba(15,23,42,0.22)">
        <circle cx="43" cy="20" r="3.4" fill="#ffffff" fillOpacity="0.8" />
        <path d="M14 23 19 15 22 19.5 24.5 16 29 23Z" fill="#ffffff" fillOpacity="0.8" />
        <path d="M19 44 31 22 38 33 43 25 50 44Z" fill="#ffffff" fillOpacity="0.97" />
        <path d="M31 22 34.5 28 29 37Z" fill="#ffffff" fillOpacity="0.55" />
      </HexFrame>
    </svg>
  )
}

export function BadgeCityWanderer({ className = 'badge-art' }: BadgeArtProps) {
  return (
    <svg className={className} viewBox="0 0 64 64" aria-hidden="true">
      <HexFrame fill="var(--yellow)" rim="rgba(15,23,42,0.22)">
        <rect x="16.5" y="32" width="9" height="16" fill="#ffffff" fillOpacity="0.95" />
        <rect x="27.5" y="19" width="10" height="29" fill="#ffffff" fillOpacity="0.97" />
        <rect x="39.5" y="27" width="9" height="21" fill="#ffffff" fillOpacity="0.95" />
        <g fill="var(--yellow)">
          <rect x="19" y="36" width="2" height="2" />
          <rect x="22.5" y="36" width="2" height="2" />
          <rect x="19" y="41" width="2" height="2" />
          <rect x="22.5" y="41" width="2" height="2" />
          <rect x="30.5" y="23" width="2" height="2" />
          <rect x="34" y="23" width="2" height="2" />
          <rect x="30.5" y="28.5" width="2" height="2" />
          <rect x="34" y="28.5" width="2" height="2" />
          <rect x="30.5" y="34" width="2" height="2" />
          <rect x="34" y="34" width="2" height="2" />
          <rect x="42" y="31" width="2" height="2" />
          <rect x="45" y="31" width="2" height="2" />
          <rect x="42" y="36" width="2" height="2" />
          <rect x="45" y="36" width="2" height="2" />
        </g>
      </HexFrame>
    </svg>
  )
}

export function BadgeCoastalWalker({ className = 'badge-art' }: BadgeArtProps) {
  return (
    <svg className={className} viewBox="0 0 64 64" aria-hidden="true">
      <HexFrame fill="#3f7fa6" rim="rgba(15,23,42,0.22)">
        <circle cx="32" cy="22" r="6.5" fill="#ffffff" fillOpacity="0.9" />
        <path d="M11 36c3 0 3-3.2 6-3.2s3 3.2 6 3.2 3-3.2 6-3.2 3 3.2 6 3.2 3-3.2 6-3.2 3 3.2 6 3.2" fill="none" stroke="#ffffff" strokeWidth="2.2" strokeLinecap="round" strokeOpacity="0.95" />
        <path d="M11 45c3 0 3-3.2 6-3.2s3 3.2 6 3.2 3-3.2 6-3.2 3 3.2 6 3.2 3-3.2 6-3.2 3 3.2 6 3.2" fill="none" stroke="#ffffff" strokeWidth="2.2" strokeLinecap="round" strokeOpacity="0.7" />
      </HexFrame>
    </svg>
  )
}
