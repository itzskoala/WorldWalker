// Top-level routing - native email/password auth (src/auth/AuthContext.tsx)
// is the only auth state now. /login, /signup, and the marketing
// placeholders (/explore, /about, /pricing, /terms, /privacy -
// MarketingHeader.tsx's nav plus the footer/auth-form legal links) are
// real, separate pages reachable regardless of auth state; everything
// else lives under / as one authenticated app shell (tabs + Trip Detail
// are internal state, not routes - see AppShell.tsx).

import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider, useAuth } from './auth/AuthContext'
import { LoginPage } from './pages/LoginPage'
import { SignupPage } from './pages/SignupPage'
import { LandingPage } from './pages/LandingPage'
import { ExplorePage } from './pages/ExplorePage'
import { AboutPage } from './pages/AboutPage'
import { PricingPage } from './pages/PricingPage'
import { TermsPage } from './pages/TermsPage'
import { PrivacyPage } from './pages/PrivacyPage'
import { ForgotPasswordPage } from './pages/ForgotPasswordPage'
import { AppShell } from './AppShell'

function RequireAuth({ children }: { children: React.ReactNode }) {
  const { status } = useAuth()

  if (status === 'loading') {
    return (
      <div className="auth-loading" aria-hidden="false">
        <span className="spinner" aria-hidden="true" />
      </div>
    )
  }

  // auth-ui.js's own rule: anyone who can't be authenticated goes
  // straight to /signup (a full navigation there, a client-side redirect
  // here - same destination either way).
  if (status === 'unauthenticated') return <Navigate to="/signup" replace />

  return <>{children}</>
}

// "/" is the one route that forks on auth state instead of requiring it
// outright - LandingPage when signed out (the public, marketing entry
// point), AppShell when signed in (the real dashboard already lives at
// "/" for a logged-in user). Every other path still goes through
// RequireAuth below, same as before - a deep link while signed out still
// bounces to /signup, not the landing page.
function RootRoute() {
  const { status } = useAuth()

  if (status === 'loading') {
    return (
      <div className="auth-loading" aria-hidden="false">
        <span className="spinner" aria-hidden="true" />
      </div>
    )
  }

  return status === 'authenticated' ? <AppShell /> : <LandingPage />
}

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/signup" element={<SignupPage />} />
          <Route path="/explore" element={<ExplorePage />} />
          <Route path="/about" element={<AboutPage />} />
          <Route path="/pricing" element={<PricingPage />} />
          <Route path="/terms" element={<TermsPage />} />
          <Route path="/privacy" element={<PrivacyPage />} />
          <Route path="/forgot-password" element={<ForgotPasswordPage />} />
          <Route path="/" element={<RootRoute />} />
          <Route
            path="/*"
            element={
              <RequireAuth>
                <AppShell />
              </RequireAuth>
            }
          />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  )
}

export default App
