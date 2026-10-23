// The logged-in navbar - stripped down to just the brand mark/logo and
// an empty placeholder slot on the right. The Google Health connection
// status (and its Connect/Disconnect toggle) now lives solely on
// ConnectionsPage.tsx - no second instance up here. MarketingHeader.tsx
// is the separate, unrelated signed-out navbar; this one only ever
// renders inside AppShell, which only mounts once someone is actually
// signed in.

import { IconMountain } from './icons'

export function Topbar() {
  return (
    <header className="topbar">
      <div className="brand">
        <IconMountain className="icon brand-mark" />
        <span className="brand-name">WorldWalker</span>
      </div>

      {/* Reserved for whatever goes here next (search, notifications,
          account menu) - intentionally empty for now. */}
      <div className="topbar-placeholder" aria-hidden="true" />
    </header>
  )
}
