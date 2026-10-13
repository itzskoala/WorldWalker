// A photo library preview of places walked - shows the first few
// postcards, with "View all" opening the full Postcards screen. Real
// postcard generation/upload logic doesn't exist yet - POSTCARDS is
// stand-in photo data (see src/mock/profileMock.ts) until that's built.

import { IconImages } from '../icons'
import { ProfileSectionCard } from './ProfileSectionCard'
import { photoUrl, POSTCARDS, PROFILE_POSTCARD_PREVIEW_COUNT } from '../../mock/profileMock'

interface PostcardsLibraryProps {
  onViewAll: () => void
}

export function PostcardsLibrary({ onViewAll }: PostcardsLibraryProps) {
  const preview = POSTCARDS.slice(0, PROFILE_POSTCARD_PREVIEW_COUNT)

  return (
    <ProfileSectionCard icon={<IconImages className="icon icon-sm" />} title="Postcards Library" onViewAll={POSTCARDS.length > preview.length ? onViewAll : undefined}>
      {POSTCARDS.length === 0 ? (
        <p className="profile-empty">Your postcard library is empty — finish a walk to collect your first one.</p>
      ) : (
        <div className="postcard-grid">
          {preview.map((card) => (
            <figure className="postcard-tile" key={card.id}>
              <img src={photoUrl(card.photoSeed, 220, 220)} alt="" />
              <figcaption>
                <span className="postcard-place">{card.place}</span>
                <span className="postcard-region">{card.region}</span>
              </figcaption>
            </figure>
          ))}
        </div>
      )}
    </ProfileSectionCard>
  )
}
