// One tile in the My Walks stats row (HomePage.tsx) - an icon, a bold
// headline number, and a quiet label underneath. Deliberately its own
// bordered white card, not a tinted pill like ProfileStatsRow.tsx's -
// Trip Detail's own stats already settled on separate white pills over a
// merged panel (see components/profile/ProfileStatsRow.tsx's sibling
// note on TripDetailPage.tsx), and this row follows the same precedent.

import type { ReactNode } from 'react'

interface StatCardProps {
  icon: ReactNode
  value: string
  label: string
}

export function StatCard({ icon, value, label }: StatCardProps) {
  return (
    <div className="walks-stat-card">
      <span className="walks-stat-icon">{icon}</span>
      <span className="walks-stat-value">{value}</span>
      <span className="walks-stat-label">{label}</span>
    </div>
  )
}
