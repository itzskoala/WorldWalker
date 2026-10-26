// The header shared by every signed-out-reachable page: the landing page,
// /login, /signup, and the Explore/About Us/Pricing placeholders
// (PlaceholderPage.tsx). Logo left; everything else - Explore/About Us/
// Pricing, then Sign in/Sign up (or the user's own avatar when a session
// exists) - grouped together on the far right, each a real route (not an
// in-page anchor). This header can render while signed in too, since
// someone can still reach /login or one of the placeholder pages
// directly by URL without RequireAuth (App.tsx) ever stepping in.

import { Link, NavLink } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

const NAV_LINKS = [
  { label: 'Explore', to: '/explore' },
  { label: 'About Us', to: '/about' },
  { label: 'Pricing', to: '/pricing' },
]

interface MarketingHeaderProps {
  // LandingPage.tsx passes these so its header's Sign in/Sign up open
  // AuthModal.tsx in place instead of navigating away - every other page
  // that renders this header has no modal mounted, so it falls back to
  // real links to /login and /signup.
  onSignIn?: () => void
  onSignUp?: () => void
}

export function MarketingHeader({ onSignIn, onSignUp }: MarketingHeaderProps) {
  const { status, user } = useAuth()
  const signedIn = status === 'authenticated' && user

  return (
    <header className="topbar marketing-header">
      <Link to="/" className="brand">
        <span className="brand-name">WorldWalker</span>
      </Link>

      <div className="marketing-header-right">
        <nav className="marketing-nav">
          {NAV_LINKS.map(({ label, to }) => (
            <NavLink key={label} to={to} className={({ isActive }) => `marketing-nav-link${isActive ? ' is-active' : ''}`}>
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="marketing-header-actions">
          {signedIn ? (
            <Link to="/" className="marketing-header-avatar" aria-label="Your profile">
              {user.profile_photo ? (
                <img src={user.profile_photo} alt="" />
              ) : (
                <span>{(user.username || user.email || '?').charAt(0).toUpperCase()}</span>
              )}
            </Link>
          ) : (
            <>
              {onSignIn ? (
                <button type="button" className="marketing-nav-link" onClick={onSignIn}>
                  Sign in
                </button>
              ) : (
                <Link to="/login" className="marketing-nav-link">
                  Sign in
                </Link>
              )}
              {onSignUp ? (
                <button type="button" className="btn-header-cta" onClick={onSignUp}>
                  Sign up
                </button>
              ) : (
                <Link to="/signup" className="btn-header-cta">
                  Sign up
                </Link>
              )}
            </>
          )}
        </div>
      </div>
    </header>
  )
}
