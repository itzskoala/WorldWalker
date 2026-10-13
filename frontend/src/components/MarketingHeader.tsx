// The signed-out header (landing + auth pages) - logo left, Explore/How
// It Works center, Log In/Sign Up right. The two nav links point at
// LandingPage.tsx's own sections (#explore, #how-it-works): a plain
// anchor when already on the landing page (native smooth scroll - see
// styles/style.css's `scroll-behavior: smooth`), or a router Link back
// to "/" with that hash when on /login or /signup instead - LandingPage
// itself scrolls to the hash on mount for that second case.

import { Link, useLocation } from 'react-router-dom'
import { IconFootprintMark } from './icons'

const NAV_LINKS = [
  { label: 'Explore', hash: '#explore' },
  { label: 'How It Works', hash: '#how-it-works' },
]

export function MarketingHeader() {
  const { pathname } = useLocation()
  const onLandingPage = pathname === '/'
  const onAuthPage = pathname === '/login' || pathname === '/signup'

  return (
    <header className="topbar marketing-header">
      <Link to="/" className="brand">
        <IconFootprintMark className="brand-mark" />
        <span className="brand-name">WorldWalker</span>
      </Link>

      <nav className="marketing-nav">
        {NAV_LINKS.map(({ label, hash }) =>
          onLandingPage ? (
            <a key={label} href={hash} className="marketing-nav-link">
              {label}
            </a>
          ) : (
            <Link key={label} to={{ pathname: '/', hash }} className="marketing-nav-link">
              {label}
            </Link>
          ),
        )}
      </nav>

      <div className="marketing-header-actions">
        <Link to="/login" className="btn-header-cta" aria-current={onAuthPage && pathname === '/login' ? 'page' : undefined}>
          Sign In
        </Link>
        <Link to="/signup" className="btn-header-cta btn-header-cta--primary" aria-current={onAuthPage && pathname === '/signup' ? 'page' : undefined}>
          Sign Up
        </Link>
      </div>
    </header>
  )
}
