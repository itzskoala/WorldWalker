const LEVELS = [
  { label: 'Make it more complicated', color: 'var(--red)' },
  { label: 'Okay', color: 'var(--yellow)' },
  { label: "Lookin' good", color: 'var(--blue)' },
  { label: 'Perfection!', color: 'var(--green)' },
] as const

function scorePassword(value: string): number {
  let score = 0
  if (value.length >= 8) score++
  if (/[A-Z]/.test(value) && /[a-z]/.test(value)) score++
  if (/[0-9]/.test(value)) score++
  if (/[^A-Za-z0-9]/.test(value)) score++
  if (value.length < 6 && score > 1) score = 1
  return score
}

interface PasswordStrengthMeterProps {
  password: string
}

export function PasswordStrengthMeter({ password }: PasswordStrengthMeterProps) {
  if (!password) return null

  const score = Math.max(1, scorePassword(password))
  const level = LEVELS[score - 1]

  return (
    <div className="password-strength">
      <div className="password-strength-track">
        <div className="password-strength-fill" style={{ width: `${score * 25}%`, backgroundColor: level.color }} />
      </div>
      <p className="password-strength-label" style={{ color: level.color }}>
        {level.label}
      </p>
      <p className="password-strength-hint">Use 8 or more letters, numbers and symbols</p>
    </div>
  )
}
