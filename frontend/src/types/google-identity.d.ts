// Minimal ambient types for the parts of Google Identity Services this
// app actually uses (accounts.google.com/gsi/client, loaded via a plain
// <script> tag - no npm package ships types for it). Only initialize()
// and renderButton() are called anywhere in this codebase.

interface GoogleIdCredentialResponse {
  credential: string
}

interface GoogleIdConfig {
  client_id: string
  callback: (response: GoogleIdCredentialResponse) => void
  use_fedcm_for_button?: boolean
}

interface GoogleIdButtonConfig {
  type?: 'standard' | 'icon'
  theme?: 'outline' | 'filled_blue' | 'filled_black'
  size?: 'large' | 'medium' | 'small'
  shape?: 'rectangular' | 'pill' | 'circle' | 'square'
  text?: 'signin_with' | 'signup_with' | 'continue_with' | 'signin'
  width?: number
}

interface Window {
  google?: {
    accounts: {
      id: {
        initialize: (config: GoogleIdConfig) => void
        renderButton: (parent: HTMLElement, options: GoogleIdButtonConfig) => void
      }
    }
  }
}
