// My Walks' top banner (HomePage.tsx) - a dark mountain illustration
// rather than a stock photo, same hand-drawn line-art language as
// Sidebar.tsx's own SidebarMountains flourish (just a bigger, moodier
// version of it) instead of pulling in an external image asset.

import { IconMap } from '../icons'

interface HeroBannerProps {
  onViewMap: () => void
}

function HeroMountains() {
  return (
    <svg className="walks-hero-art" viewBox="0 0 800 260" preserveAspectRatio="xMidYMax slice" aria-hidden="true">
      <path d="M0 260 130 120 230 210 300 150 420 260Z" fill="#163B33" />
      <path d="M90 260 260 70 360 190 430 110 560 260Z" fill="#1D4B40" />
      <path d="M260 260 420 90 520 200 600 120 800 260Z" fill="#275D50" />
      <path d="M480 260 620 110 700 210 760 160 800 260Z" fill="#2F6E5E" />
    </svg>
  )
}

export function HeroBanner({ onViewMap }: HeroBannerProps) {
  return (
    <section className="walks-hero">
      <HeroMountains />
      <div className="walks-hero-scrim" />
      <div className="walks-hero-content">
        <h1 className="walks-hero-title">Your journeys, all in one place</h1>
        <p className="walks-hero-subtitle">Track every walk you've taken, from first step to final checkpoint.</p>
      </div>
      <button type="button" className="walks-hero-cta" onClick={onViewMap}>
        <IconMap className="icon icon-sm" />
        View on Map
      </button>
    </section>
  )
}
