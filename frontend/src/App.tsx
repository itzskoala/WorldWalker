// Top-level routing - a port of how app.py/auth-ui.js split things today:
// /login and /signup are real, separate pages; everything else lives
// under / as one authenticated app shell (tabs + Trip Detail are internal
// state, not routes, matching the vanilla app exactly - see AppShell.tsx).

import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider, useAuth } from './auth/AuthContext'
import { LoginPage } from './pages/LoginPage'
import { SignupPage } from './pages/SignupPage'
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

  // auth-ui.js's own rule: anyone Auth.init() can't authenticate goes
  // straight to /signup (a full navigation there, a client-side redirect
  // here - same destination either way).
  if (status === 'unauthenticated') return <Navigate to="/signup" replace />

  return <>{children}</>
}

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/signup" element={<SignupPage />} />
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
