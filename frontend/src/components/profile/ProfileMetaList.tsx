// The small lifetime-steps/postcards/member-since list next to the
// avatar on ProfilePage.tsx. Purely presentational - all three values
// come straight off the User record (types/user.ts).

import { IconCalendar, IconImages, IconShoe } from '../icons'

interface ProfileMetaListProps {
  lifetimeSteps: number
  postcardsSum: number
  memberSince: string | undefined
}

function formatMemberSince(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString(undefined, { month: 'long', day: 'numeric', year: 'numeric' })
}

export function ProfileMetaList({ lifetimeSteps, postcardsSum, memberSince }: ProfileMetaListProps) {
  return (
    <div className="profile-page-stats">
      <span className="profile-page-stat">
        <IconShoe className="icon icon-sm" />
        {lifetimeSteps.toLocaleString()} lifetime steps
      </span>
      <span className="profile-page-stat">
        <IconImages className="icon icon-sm" />
        {postcardsSum.toLocaleString()} postcards
      </span>
      <span className="profile-page-stat">
        <IconCalendar className="icon icon-sm" />
        Member since {memberSince ? formatMemberSince(memberSince) : '—'}
      </span>
    </div>
  )
}
