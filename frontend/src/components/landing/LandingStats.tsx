const STATS = [
  { value: '2M+', label: 'Steps' },
  { value: '1K+', label: 'Postcards sent' },
  { value: '20', label: 'Users' },
]

export function LandingStats() {
  return (
    <ul className="landing-stats">
      {STATS.map(({ value, label }) => (
        <li className="landing-stat" key={label}>
          <span className="landing-stat-value">{value}</span>
          <span className="landing-stat-label">{label}</span>
        </li>
      ))}
    </ul>
  )
}
