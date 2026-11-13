import { useState } from 'react'
import { MarketingHeader } from '../MarketingHeader'
import { MarketingFooter } from '../MarketingFooter'
import { AuthModal, type AuthModalMode } from '../AuthModal'

interface PlaceholderPageProps {
  title: string
  body: string
}

export function PlaceholderPage({ title, body }: PlaceholderPageProps) {
  const [authModalMode, setAuthModalMode] = useState<AuthModalMode | null>(null)

  return (
    <div className="landing">
      <MarketingHeader onSignIn={() => setAuthModalMode('login')} onSignUp={() => setAuthModalMode('signup')} />
      <main className="landing-placeholder">
        <h1 className="landing-placeholder-title">{title}</h1>
        <p className="landing-placeholder-body">{body}</p>

        {authModalMode && (
          <AuthModal mode={authModalMode} onClose={() => setAuthModalMode(null)} onSwitchMode={setAuthModalMode} />
        )}
      </main>
      <MarketingFooter />
    </div>
  )
}
