const STATS = [
  { value: '2M+', label: 'Steps' },
  { value: '195', label: 'Countries' },
  { value: '7', label: 'Continents' },
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
