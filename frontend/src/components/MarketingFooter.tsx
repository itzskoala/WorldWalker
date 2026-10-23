const FOOTER_LINKS = [
  { label: 'Blog', href: '#' },
  { label: 'X (Twitter)', href: '#' },
  { label: 'Support', href: 'mailto:support@worldwalker.app' },
  { label: 'Privacy', href: '#' },
  { label: 'Terms', href: '#' },
]

export function MarketingFooter() {
  return (
    <footer className="marketing-footer">
      <div className="marketing-footer-inner">
        <span className="marketing-footer-copyright">&copy; 2026 WorldWalker</span>
        <nav className="marketing-footer-links" aria-label="Footer">
          {FOOTER_LINKS.map(({ label, href }) => (
            <a key={label} href={href} className="marketing-footer-link">
              {label}
            </a>
          ))}
        </nav>
      </div>
    </footer>
  )
}
