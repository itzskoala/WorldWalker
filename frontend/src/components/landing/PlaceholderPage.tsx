import { MarketingHeader } from '../MarketingHeader'
import { MarketingFooter } from '../MarketingFooter'

interface PlaceholderPageProps {
  title: string
  body: string
}

export function PlaceholderPage({ title, body }: PlaceholderPageProps) {
  return (
    <div className="landing">
      <MarketingHeader />
      <main className="landing-placeholder">
        <h1 className="landing-placeholder-title">{title}</h1>
        <p className="landing-placeholder-body">{body}</p>
      </main>
      <MarketingFooter />
    </div>
  )
}
