import { WorldWindGlobe } from '../WorldWindGlobe'

export function CreateHero() {
  return (
    <section className="globe-header">
      <WorldWindGlobe />
      <div className="globe-header-scrim" aria-hidden="true" />
      <div className="globe-header-text">
        <h1 className="hero-title">Walk the World</h1>
        <p className="hero-sub">Turn your real, everyday steps into a journey across the globe.</p>
      </div>
    </section>
  )
}
