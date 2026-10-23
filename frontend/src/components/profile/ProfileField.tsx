// One labeled text input on ProfilePage.tsx's account form - Username,
// First name, Last name, Bio all render through this one component
// rather than repeating the label+input markup four times.

interface ProfileFieldProps {
  id: string
  label: string
  value: string
  onChange: (value: string) => void
}

export function ProfileField({ id, label, value, onChange }: ProfileFieldProps) {
  return (
    <div className="profile-page-field">
      <label className="profile-page-label" htmlFor={id}>
        {label}
      </label>
      <input id={id} className="profile-page-input" value={value} onChange={(e) => onChange(e.target.value)} />
    </div>
  )
}
