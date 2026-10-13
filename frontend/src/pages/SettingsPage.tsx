// Settings screen - the new home for controls that used to live directly
// in the topbar (theme, email checkpoint alerts) now that Topbar.tsx is
// deliberately minimal, plus sign-out and Support - one sidebar entry
// (the gear icon) covers both, not two separate destinations. The Google
// Health connection itself lives on its own "My Connections" screen now
// (ConnectionsPage.tsx), its own sidebar entry, same as every other tab.

import { useAuth } from '../auth/AuthContext'
import { useTheme } from '../hooks/useTheme'
import { IconLifeBuoy, IconLock } from '../components/icons'

const FAQS = [
  {
    question: 'How does a walk track my real steps?',
    answer: 'Connect Google Health from My Connections - once connected, your real steps move every active walk along its route.',
  },
  {
    question: 'Can I run more than one walk at a time?',
    answer: 'Yes - start as many as you like from Explore. Real steps credit every walk that is currently active, not paused.',
  },
  {
    question: 'Where do my badges and postcards come from?',
    answer: 'Finishing a walk, and reaching checkpoints along the way, add to the collection on your Profile.',
  },
]

interface SettingsPageProps {
  onOpenEmailAlerts: () => void
}

export function SettingsPage({ onOpenEmailAlerts }: SettingsPageProps) {
  const { theme, toggleTheme } = useTheme()
  const { logout } = useAuth()

  return (
    <section className="screen" id="screen-settings" aria-label="Settings">
      <div className="screen-inner">
        <div className="screen-header">
          <h1 className="screen-title">Settings</h1>
        </div>

        <section className="surface-card settings-row">
          <div className="settings-row-text">
            <h2 className="settings-row-title">Appearance</h2>
            <p className="settings-row-body">Switch between light and dark.</p>
          </div>
          <button
            type="button"
            className="theme-toggle"
            aria-label={theme === 'light' ? 'Switch to dark mode' : 'Switch to light mode'}
            aria-pressed={theme === 'light'}
            onClick={toggleTheme}
          >
            <span className="theme-toggle-track">
              <svg className="theme-toggle-icon theme-toggle-sun" viewBox="0 0 24 24" fill="none">
                <circle cx="12" cy="12" r="4.5" stroke="currentColor" strokeWidth="1.8" />
                <path
                  d="M12 2.5v2.4M12 19.1v2.4M4.2 4.2l1.7 1.7M18.1 18.1l1.7 1.7M2.5 12h2.4M19.1 12h2.4M4.2 19.8l1.7-1.7M18.1 5.9l1.7-1.7"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                />
              </svg>
              <svg className="theme-toggle-icon theme-toggle-moon" viewBox="0 0 24 24" fill="none">
                <path d="M20 14.5A8.5 8.5 0 1 1 9.5 4a7 7 0 0 0 10.5 10.5Z" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
              </svg>
              <span className="theme-toggle-knob" />
            </span>
          </button>
        </section>

        <section className="surface-card settings-row">
          <div className="settings-row-text">
            <h2 className="settings-row-title">Email checkpoint alerts</h2>
            <p className="settings-row-body">Get an email of your own whenever a walk reaches a new checkpoint.</p>
          </div>
          <button type="button" className="btn btn-outline" onClick={onOpenEmailAlerts}>
            Manage
          </button>
        </section>

        <section className="surface-card settings-row">
          <div className="settings-row-text">
            <h2 className="settings-row-title">Sign out</h2>
            <p className="settings-row-body">Sign out of WorldWalker on this device.</p>
          </div>
          <button type="button" className="btn btn-outline" onClick={() => logout()}>
            <IconLock className="icon icon-sm" />
            Log out
          </button>
        </section>

        <section className="surface-card support-contact">
          <IconLifeBuoy className="icon support-contact-icon" />
          <div>
            <h2 className="settings-row-title">Need help?</h2>
            <p className="settings-row-body">
              Write to us at <a href="mailto:support@worldwalker.app">support@worldwalker.app</a> and we'll get back to you.
            </p>
          </div>
        </section>

        <section className="surface-card">
          <h2 className="profile-section-title">Frequently asked</h2>
          <dl className="support-faq-list">
            {FAQS.map(({ question, answer }) => (
              <div className="support-faq-item" key={question}>
                <dt>{question}</dt>
                <dd>{answer}</dd>
              </div>
            ))}
          </dl>
        </section>
      </div>
    </section>
  )
}
