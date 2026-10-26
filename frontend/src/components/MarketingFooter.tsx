import { Link } from 'react-router-dom'

const EXTERNAL_LINKS = [
  { label: 'Blog', href: '#' },
  { label: 'X (Twitter)', href: '#' },
  { label: 'Support', href: 'mailto:support@worldwalker.app' },
]

export function MarketingFooter() {
  return (
    <footer className="marketing-footer">
      <div className="marketing-footer-inner">
        <span className="marketing-footer-copyright">&copy; 2026 WorldWalker</span>
        <nav className="marketing-footer-links" aria-label="Footer">
          {EXTERNAL_LINKS.map(({ label, href }) => (
            <a key={label} href={href} className="marketing-footer-link">
              {label}
            </a>
          ))}
          <Link to="/privacy" className="marketing-footer-link">
            Privacy
          </Link>
          <Link to="/terms" className="marketing-footer-link">
            Terms
          </Link>
        </nav>
      </div>
    </footer>
  )
}
