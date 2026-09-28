// Misc request/response shapes that don't belong to trip.ts or user.ts -
// notifications/schemas.py's EmailConfig* and auth/router.py's Google
// Health status/disconnect routes.

export interface EmailConfigRequest {
  smtp_host: string
  smtp_port: number
  smtp_username: string
  smtp_password: string
}

export interface EmailConfigStatus {
  configured: boolean
}

export interface GoogleHealthStatus {
  connected: boolean
}

export interface GoogleAuthStartResponse {
  auth_url: string
}

/** Every route in this app reports errors one of two ways: FastAPI's own
 * HTTPException/validation-error body ({detail: ...}) on accounts/auth/
 * notifications routes, or a plain {error: string} JSONResponse on a
 * handful of app.py routes (search/reverse geocode, journey start/state/
 * pause/resume/delete) - see e.g. app.py's start_journey(). Both are
 * handled by src/api/httpClient.ts's parseErrorMessage(). */
export interface ApiErrorBody {
  detail?: string | Array<{ msg?: string }>
  error?: string
}
