// Shared wrapper for PrivacyPage/TermsPage - same header/footer/auth-modal
// setup as PlaceholderPage.tsx (Sign in/Sign up open AuthModal in place,
// never navigate away), just a left-aligned article layout instead of a
// centered one-liner, since these pages have real, long-form content.

import { useState } from 'react'
import { MarketingHeader } from '../MarketingHeader'
import { MarketingFooter } from '../MarketingFooter'
import { AuthModal, type AuthModalMode } from '../AuthModal'

interface LegalPageProps {
  title: string
  lastUpdated: string
  summary: string
  children: React.ReactNode
}

export function LegalPage({ title, lastUpdated, summary, children }: LegalPageProps) {
  const [authModalMode, setAuthModalMode] = useState<AuthModalMode | null>(null)

  return (
    <div className="landing">
      <MarketingHeader onSignIn={() => setAuthModalMode('login')} onSignUp={() => setAuthModalMode('signup')} />

      <main className="legal-page">
        <h1 className="legal-title">{title}</h1>
        <p className="legal-updated">Last updated: {lastUpdated}</p>

        <div className="legal-summary">
          <h2 className="legal-summary-label">Summary</h2>
          <p>{summary}</p>
        </div>

        <div className="legal-body">{children}</div>

        {authModalMode && (
          <AuthModal mode={authModalMode} onClose={() => setAuthModalMode(null)} onSwitchMode={setAuthModalMode} />
        )}
      </main>

      <MarketingFooter />
    </div>
  )
}
