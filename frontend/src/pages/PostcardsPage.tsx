// Full postcard library - the destination for the Profile screen's
// "View all" link, and its own sidebar entry. POSTCARDS is mock data
// (see src/mock/profileMock.ts) until postcard collection has a backend.

import { photoUrl, POSTCARDS } from '../mock/profileMock'

export function PostcardsPage() {
  return (
    <section className="screen" id="screen-postcards" aria-label="Postcards">
      <div className="screen-inner screen-inner-wide">
        <div className="screen-header">
          <h1 className="screen-title">Postcards</h1>
        </div>

        {POSTCARDS.length === 0 ? (
          <section className="surface-card">
            <p className="profile-empty">Your postcard library is empty — finish a walk to collect your first one.</p>
          </section>
        ) : (
          <div className="postcard-grid postcard-grid-full">
            {POSTCARDS.map((card) => (
              <figure className="postcard-tile" key={card.id}>
                <img src={photoUrl(card.photoSeed, 320, 320)} alt="" />
                <figcaption>
                  <span className="postcard-place">{card.place}</span>
                  <span className="postcard-region">{card.region}</span>
                </figcaption>
              </figure>
            ))}
          </div>
        )}
      </div>
    </section>
  )
}
