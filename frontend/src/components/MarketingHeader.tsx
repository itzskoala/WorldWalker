// The signed-out header (login/signup pages only) - a port of Strava's
// own marketing nav: brand left, nav links center, one CTA right. The
// nav links have no pages behind them yet (WorldWalker has no marketing
// site, just the app), so they're inert placeholders for now rather than
// routes that would 404.

import { Link } from 'react-router-dom'

const NAV_LINKS = ['Features', 'Explore Feature', 'About']

export function MarketingHeader() {
  return (
    <header className="topbar marketing-header">
      <div className="brand">
        <span className="brand-mark">🌍</span>
        <span className="brand-name">WorldWalker</span>
      </div>

      <nav className="marketing-nav">
        {NAV_LINKS.map((label) => (
          <a key={label} href="#" className="marketing-nav-link" onClick={(e) => e.preventDefault()}>
            {label}
          </a>
        ))}
      </nav>

      <Link to="/login" className="btn-header-cta">
        Log In
      </Link>
    </header>
  )
}
