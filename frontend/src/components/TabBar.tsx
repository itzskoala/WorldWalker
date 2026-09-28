// Port of web/templates/index.html's <nav class="tab-bar"> +
// web/static/js/nav.js. Tab state lives in AppShell (not the URL) - same
// as the vanilla version, where switching tabs never touches the URL.

export type ScreenName = 'home' | 'create' | 'profile'

interface TabBarProps {
  active: ScreenName
  onChange: (screen: ScreenName) => void
}

const TABS: { name: ScreenName; label: string }[] = [
  { name: 'home', label: 'Home' },
  { name: 'create', label: 'Create' },
  { name: 'profile', label: 'Profile' },
]

function TabIcon({ name }: { name: ScreenName }) {
  if (name === 'home') {
    return (
      <svg className="icon" viewBox="0 0 24 24" fill="none">
        <path d="m4 11 8-7 8 7" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M6 10v9a1 1 0 0 0 1 1h3v-6h4v6h3a1 1 0 0 0 1-1v-9" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    )
  }
  if (name === 'create') {
    return (
      <svg className="icon" viewBox="0 0 24 24" fill="none">
        <path d="M12 5v14M5 12h14" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      </svg>
    )
  }
  return (
    <svg className="icon" viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="8" r="3.5" stroke="currentColor" strokeWidth="1.8" />
      <path d="M4.5 20c1.3-3.6 4.3-5.5 7.5-5.5s6.2 1.9 7.5 5.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  )
}

export function TabBar({ active, onChange }: TabBarProps) {
  return (
    <nav className="tab-bar" aria-label="Main">
      {TABS.map((tab) => (
        <button
          key={tab.name}
          type="button"
          className={`tab-btn${active === tab.name ? ' is-active' : ''}`}
          aria-current={active === tab.name ? 'page' : undefined}
          onClick={() => onChange(tab.name)}
        >
          <TabIcon name={tab.name} />
          <span>{tab.label}</span>
        </button>
      ))}
    </nav>
  )
}
