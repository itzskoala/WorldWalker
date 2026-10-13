// "My Connections" - the sidebar's own destination for the Google Health
// connection (hooks/useGoogleHealthConnection.ts - the existing backend,
// the same instance Topbar.tsx's status pill reads, not a second
// implementation). Used to live as a row on Settings; broken out into
// its own screen so the sidebar entry can navigate here directly, like
// every other sidebar tab.

import type { GoogleHealthConnection } from '../hooks/useGoogleHealthConnection'
import { IconConnection } from '../components/icons'

interface ConnectionsPageProps {
  connection: GoogleHealthConnection
}

export function ConnectionsPage({ connection }: ConnectionsPageProps) {
  const { connected, connecting, error, toggle } = connection

  return (
    <section className="screen" id="screen-connections" aria-label="My Connections">
      <div className="screen-inner">
        <div className="screen-header">
          <h1 className="screen-title">My Connections</h1>
        </div>

        <section className="surface-card settings-row">
          <div className="settings-row-text settings-row-text-icon">
            <span className="connections-icon">
              <IconConnection className="icon" />
            </span>
            <div>
              <h2 className="settings-row-title">Google Health</h2>
              <p className="settings-row-body">
                {connected ? 'Connected - your real steps move your active walks.' : 'Not connected - connect to credit real steps to your walks.'}
              </p>
            </div>
          </div>
          <button type="button" className={`btn btn-connect${connected ? ' is-connected' : ''}${connecting ? ' is-loading' : ''}`} onClick={toggle}>
            <span>{connected ? 'Disconnect' : 'Connect'}</span>
          </button>
        </section>

        {error && (
          <p className="connections-error" role="alert">
            {error}
          </p>
        )}
      </div>
    </section>
  )
}
