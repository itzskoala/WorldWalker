// Quiet nudge back to Create, anchoring the bottom of the right column
// instead of leaving it empty next to the favorites list.

import { IconChevronRight, IconMountain } from '../icons'

interface ExploreCtaProps {
  onExplore: () => void
}

export function ExploreCta({ onExplore }: ExploreCtaProps) {
  return (
    <section className="surface-card explore-cta">
      <IconMountain className="icon explore-cta-icon" />
      <h2 className="explore-cta-title">Keep exploring</h2>
      <p className="explore-cta-body">Every walk, every postcard, every badge is a new story. Your next adventure is just a step away.</p>
      <button type="button" className="btn explore-cta-btn" onClick={onExplore}>
        Explore Walks
        <IconChevronRight className="icon icon-sm" />
      </button>
    </section>
  )
}
