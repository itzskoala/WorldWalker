// Real-time password strength meter for the signup password field - a
// port of the 4-segment design/scoring the user handed us directly
// (regex-based: length, mixed case, digits, special chars). Colors map
// onto the site's own palette (red/yellow/blue/green), which already
// matches the reference 1:1 (poor->red, fair->amber, good->blue,
// excellent->green).

const LEVELS = [
  { text: 'Empty', color: 'var(--field-border)' },
  { text: 'Poor', color: 'var(--red)' },
  { text: 'Fair', color: 'var(--yellow)' },
  { text: 'Good', color: 'var(--blue)' },
  { text: 'Excellent', color: 'var(--green)' },
] as const

function scorePassword(value: string): number {
  if (!value) return 0

  let score = 0
  if (value.length >= 8) score++
  if (/[A-Z]/.test(value) && /[a-z]/.test(value)) score++
  if (/[0-9]/.test(value)) score++
  if (/[^A-Za-z0-9]/.test(value)) score++

  // A short password can't be called "Good"/"Excellent" just because it
  // mixes character types - eight of the same rule matters more than
  // four of the others.
  if (value.length < 6 && score > 1) score = 1

  return score
}

interface PasswordStrengthMeterProps {
  password: string
}

export function PasswordStrengthMeter({ password }: PasswordStrengthMeterProps) {
  const rawScore = scorePassword(password)
  // A non-empty password that fails every rule still scored 0 - same
  // number as an actually-empty field, which showed "Empty" next to
  // visible dots in the box. Any keystroke at all should read as at
  // least "Poor", not "Empty".
  const score = password.length > 0 ? Math.max(1, rawScore) : 0
  const level = LEVELS[score]

  return (
    <div className="password-strength" aria-hidden={password.length === 0}>
      <div className="password-strength-header">
        <span>Password strength:</span>
        <span className="password-strength-label" style={{ color: score === 0 ? 'var(--ink-faint)' : level.color }}>
          {level.text}
        </span>
      </div>
      <div className="password-strength-meter">
        {[0, 1, 2, 3].map((i) => (
          <div
            key={i}
            className="password-strength-block"
            style={{ backgroundColor: i < score ? level.color : 'var(--field-border)' }}
          />
        ))}
      </div>
    </div>
  )
}
