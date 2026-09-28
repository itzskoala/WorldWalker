// GET /api/config - app.py's public, non-secret runtime config. Google
// and Apple sign-in client IDs; empty means that provider isn't
// configured for this deployment.

export interface PublicConfig {
  google_client_id: string
  apple_client_id: string
}

export async function fetchPublicConfig(): Promise<PublicConfig> {
  const res = await fetch('/api/config', { credentials: 'include' })
  if (!res.ok) return { google_client_id: '', apple_client_id: '' }
  return res.json() as Promise<PublicConfig>
}
