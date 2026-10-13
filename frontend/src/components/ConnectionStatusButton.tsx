// The Google Health connection button, top navbar only now (Topbar.tsx)
// - My Connections (Sidebar.tsx) is a plain nav item that routes to
// ConnectionsPage.tsx instead. Reads hooks/useGoogleHealthConnection.ts
// (the existing backend - AppShell owns the one instance), toggling the
// same connect/disconnect flow that page also offers.
//
// The original .btn-connect treatment (shield-check icon, blue when
// not connected, green once connected) - kept on request after a
// smaller/quieter pill read as too understated for the top nav.

import type { GoogleHealthConnection } from '../hooks/useGoogleHealthConnection'

interface ConnectionStatusButtonProps {
  connection: GoogleHealthConnection
  className?: string
}

export function ConnectionStatusButton({ connection, className = '' }: ConnectionStatusButtonProps) {
  const { connected, connecting, error, toggle } = connection

  return (
    <button
      type="button"
      className={`btn btn-connect${connected ? ' is-connected' : ''}${connecting ? ' is-loading' : ''} ${className}`.trim()}
      title={error ?? (connected ? 'Disconnect Google Health' : 'Connect Google Health')}
      onClick={toggle}
    >
      <svg className="icon" viewBox="0 0 24 24" fill="none">
        <path d="M12 2 4 5.5v6c0 5.05 3.4 9.77 8 11 4.6-1.23 8-5.95 8-11v-6L12 2Z" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
        <path d="m9 12 2 2 4-4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      <span>{connected ? 'Connected' : 'Connect'}</span>
    </button>
  )
}
