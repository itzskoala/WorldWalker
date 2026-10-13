// Walks the user has starred, not an auto-generated "top walks" list -
// this is a personal shortlist, so the empty state asks the user to make
// one rather than showing a generic "nothing here yet."

import { useState } from 'react'
import { IconClock, IconHeart, IconPin, IconRoute } from '../icons'
import { ProfileSectionCard } from './ProfileSectionCard'
import { FAVORITE_WALKS, photoUrl } from '../../mock/profileMock'

export function FavoriteWalks() {
  // Favoriting isn't backed by an API yet - toggling here only flips the
  // heart's fill for this session, same scope as ProfileHero's avatar
  // preview.
  const [unfavorited, setUnfavorited] = useState<Set<string>>(new Set())

  function toggle(id: string) {
    setUnfavorited((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  return (
    <ProfileSectionCard icon={<IconPin className="icon icon-sm" />} title="Favorite Walks">
      {FAVORITE_WALKS.length === 0 ? (
        <div className="profile-empty">
          <p className="profile-empty-title">What's your favorite walk?</p>
          <p>Star a completed walk to save it here.</p>
        </div>
      ) : (
        <ul className="favorite-walk-list">
          {FAVORITE_WALKS.map((walk) => {
            const isFavorited = !unfavorited.has(walk.id)
            return (
              <li className="favorite-walk-row" key={walk.id}>
                <img className="favorite-walk-thumb" src={photoUrl(walk.photoSeed, 96, 96)} alt="" />
                <div className="favorite-walk-info">
                  <span className="favorite-walk-name">{walk.name}</span>
                  <span className="favorite-walk-place">{walk.place}</span>
                  <span className="favorite-walk-meta">
                    <span className="favorite-walk-meta-item">
                      <IconRoute className="icon icon-sm" />
                      {walk.distanceMiles.toFixed(1)} mi
                    </span>
                    <span className="favorite-walk-meta-item">
                      <IconClock className="icon icon-sm" />
                      {walk.durationLabel}
                    </span>
                  </span>
                </div>
                <button
                  type="button"
                  className="favorite-walk-heart"
                  aria-label={isFavorited ? 'Remove from favorites' : 'Add to favorites'}
                  aria-pressed={isFavorited}
                  onClick={() => toggle(walk.id)}
                >
                  <IconHeart className="icon" filled={isFavorited} />
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </ProfileSectionCard>
  )
}
