// Persistent left sidebar nav - switches between the app's screens (tab
// state lives in AppShell, not the URL). 'home' keeps its internal name
// (HomePage, AppShell's exitTrip('home') default, etc. all still say
// "home") even though it's labeled "My Walks" here, to avoid renaming
// that plumbing just for a label change.
//
// Below the four screen links: "Connections" and Settings - two more
// screen destinations, same NavButton as the four above. Connections
// just navigates to ConnectionsPage.tsx, which reads the real Google
// Health state itself (and owns the only Connect/Disconnect button now -
// Topbar.tsx no longer has one).

import { IconCompass, IconConnection, IconFootsteps, IconGear, IconImages, IconPerson } from './icons'

export type ScreenName = 'home' | 'create' | 'postcards' | 'profile' | 'settings' | 'connections'

const ITEMS: { name: ScreenName; label: string; icon: typeof IconCompass }[] = [
  { name: 'create', label: 'Explore', icon: IconCompass },
  { name: 'home', label: 'My Walks', icon: IconFootsteps },
  { name: 'postcards', label: 'Postcards', icon: IconImages },
  { name: 'profile', label: 'Profile', icon: IconPerson },
]

const SECONDARY_ITEMS: { name: ScreenName; label: string; icon: typeof IconGear }[] = [
  { name: 'connections', label: 'Connections', icon: IconConnection },
  { name: 'settings', label: 'Settings', icon: IconGear },
]

interface SidebarProps {
  active: ScreenName
  onChange: (screen: ScreenName) => void
}

// Decorative layered-mountain mark for the sidebar footer, below - purely
// a quiet brand flourish next to the tagline, not a stand-in for any real
// icon.
function SidebarMountains() {
  return (
    <svg className="sidebar-footer-art" viewBox="0 0 120 64" aria-hidden="true">
      <path d="M0 64 26 28 46 52 58 38 78 64Z" fill="var(--ink-faint)" fillOpacity="0.18" />
      <path d="M18 64 48 22 70 50 88 30 118 64Z" fill="var(--ink-faint)" fillOpacity="0.3" />
      <path d="M42 64 64 34 80 54 96 36 118 64Z" fill="var(--ink-faint)" fillOpacity="0.5" />
    </svg>
  )
}

function NavButton({ name, label, Icon, active, onChange }: { name: ScreenName; label: string; Icon: typeof IconCompass; active: ScreenName; onChange: (s: ScreenName) => void }) {
  return (
    <button
      type="button"
      className={`sidebar-link${active === name ? ' is-active' : ''}`}
      aria-current={active === name ? 'page' : undefined}
      onClick={() => onChange(name)}
    >
      <Icon className="icon" />
      <span>{label}</span>
    </button>
  )
}

export function Sidebar({ active, onChange }: SidebarProps) {
  return (
    <nav className="sidebar" aria-label="Main">
      <div className="sidebar-links">
        {ITEMS.map(({ name, label, icon }) => (
          <NavButton key={name} name={name} label={label} Icon={icon} active={active} onChange={onChange} />
        ))}
      </div>

      <div className="sidebar-links sidebar-links-secondary">
        {SECONDARY_ITEMS.map(({ name, label, icon }) => (
          <NavButton key={name} name={name} label={label} Icon={icon} active={active} onChange={onChange} />
        ))}
      </div>

      <div className="sidebar-footer">
        <SidebarMountains />
        <p className="sidebar-footer-text">
          More steps.
          <br />
          More places.
          <br />
          A richer you.
        </p>
      </div>
    </nav>
  )
}
