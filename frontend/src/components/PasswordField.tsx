import { useState } from 'react'
import { IconEye, IconEyeOff } from './icons'
import { PasswordStrengthMeter } from './PasswordStrengthMeter'

interface PasswordFieldProps {
  id: string
  autoComplete: string
  placeholder: string
  value: string
  onChange: (value: string) => void
  showStrengthMeter?: boolean
}

export function PasswordField({ id, autoComplete, placeholder, value, onChange, showStrengthMeter }: PasswordFieldProps) {
  const [visible, setVisible] = useState(false)

  return (
    <>
      <div className="password-input">
        <input
          id={id}
          type={visible ? 'text' : 'password'}
          autoComplete={autoComplete}
          placeholder={placeholder}
          minLength={8}
          required
          value={value}
          onChange={(e) => onChange(e.target.value)}
        />
        <button
          type="button"
          className="password-toggle"
          aria-label={visible ? 'Hide password' : 'Show password'}
          onClick={() => setVisible((v) => !v)}
        >
          {visible ? <IconEyeOff /> : <IconEye />}
        </button>
      </div>
      {showStrengthMeter && <PasswordStrengthMeter password={value} />}
    </>
  )
}
