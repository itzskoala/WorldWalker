// Real content now (was a one-line "coming soon" placeholder) - written
// to match what WorldWalker actually does today: see auth/google_health_auth.py
// (the exact Google Health scopes requested), services/google_health/webhook.py
// (what we do with that data), travel_logic/description_generator.py
// (Ollama Cloud for checkpoint blurbs), travel_logic/geocoder.py +
// route_service.py (OpenStreetMap/Nominatim + OSRM), and database/models.py
// (what's actually stored). There is no self-serve "delete my account"
// button yet (see SettingsPage.tsx's own support-contact section), so
// Section 7 says to email us instead of claiming a button that doesn't
// exist.

import { LegalPage } from '../components/landing/LegalPage'

export function PrivacyPage() {
  return (
    <LegalPage
      title="Privacy Policy"
      lastUpdated="October 27, 2026"
      summary="WorldWalker turns your real steps into virtual walks along real-world routes. We don't sell your data, and we don't use it to train any AI model. If you connect Google Health, we only ever use it to credit your own steps and workouts to your own active walks - nothing else, and we never share that data with anyone. The one outside AI service we use to write checkpoint descriptions never sees your account, your steps, or your location history - only a place name and its coordinates."
    >
      <h2>1. Introduction</h2>
      <p>
        This Privacy Policy explains how WorldWalker ("we," "us," or "our") collects, uses, discloses, and
        safeguards your information when you use our website and services (the "Service"). It's incorporated by
        reference into our <a href="/terms">Terms of Service</a>. If there's anything here you don't agree with,
        please discontinue use of the Service.
      </p>

      <h2>2. How WorldWalker Works</h2>
      <p>
        WorldWalker is a small, independently-run project. Your account, your walks, and your profile are stored
        on our own servers in a Postgres database - unlike an app that runs entirely on your device, we do need to
        process your information to provide the Service. We don't run ads, we don't sell your personal information,
        and we don't use your prompts, walks, or account data to train any AI model.
      </p>

      <h2>3. Google Health Data</h2>
      <p>
        WorldWalker can connect to Google Health (from the "My Connections" screen) so your real-world steps and
        workouts move your active walks along their route. This is entirely optional - nothing in the Service
        requires it, except the one feature it exists for.
      </p>
      <p>We request exactly two Google Health scopes, both read-only:</p>
      <ul>
        <li>
          <strong>Activity and fitness (read-only):</strong> your step counts and logged exercise/workout sessions.
        </li>
        <li>
          <strong>Profile (read-only):</strong> used only to get your Google Health account's internal ID, which
          lets a Google notification tell us which WorldWalker account it belongs to. We don't use it for anything
          else - we don't pull your name, age, or any other profile field from it.
        </li>
      </ul>
      <p>
        We don't request sleep or heart-rate data. Nothing in WorldWalker uses it, so we don't ask Google for access
        to it.
      </p>
      <p>
        <strong>What we do with it:</strong> when Google notifies us of new steps or a workout, we convert that into
        forward progress on whichever of your walks are currently active, using your stride-length setting to turn
        steps into distance. We store the resulting progress - a step count, distance, and percent-complete, tied to
        a sync timestamp - not the raw Google Health records themselves.
      </p>
      <p>
        <strong>Who sees it:</strong> no one but you and WorldWalker. We never share, sell, or transfer your Google
        Health data to any third party, including the other service providers described in Section 6 below - none
        of them ever receive it.
      </p>
      <p>
        <strong>Disconnecting:</strong> the "Disconnect" button on My Connections revokes our access at Google and
        permanently deletes the stored connection from our database. Progress your walks already made stays, the
        same as if you'd simply paused - but we no longer have any access to your Google Health data from that point
        on.
      </p>

      <h2>4. Other Information We Collect</h2>
      <p>Information you provide to us:</p>
      <ul>
        <li>
          <strong>Account information:</strong> your email address and a password (we only ever store a bcrypt hash
          of it, never the password itself) - or, if you use "Sign in with Google," your Google account's unique ID
          and verified email address. We never receive your Google password, and we don't pull your name or profile
          photo from Google even when you sign in this way.
        </li>
        <li>
          <strong>Profile information:</strong> whatever you choose to add - username, first/last name, bio, profile
          photo.
        </li>
        <li>
          <strong>Walk data:</strong> the start and destination places you search for, their coordinates, the
          walking route between them, your progress, and your pace settings.
        </li>
        <li>
          <strong>Checkpoint content:</strong> place names along your route come from OpenStreetMap's Nominatim
          service; short descriptive blurbs for them are generated on our behalf by Ollama Cloud, an outside AI
          service - which only ever receives a checkpoint's place name and coordinates, never your identity, your
          account, or any Google Health data.
        </li>
        <li>
          <strong>Email alert settings (optional):</strong> if you turn on checkpoint email alerts, we store your
          own mail server address, username, and password, encrypted, and use them only to send checkpoint emails
          from your own account to yourself.
        </li>
      </ul>
      <p>Information collected automatically:</p>
      <ul>
        <li>
          <strong>Device and usage information:</strong> standard web request information (like IP address and
          browser type) that our hosting provider collects to keep the Service secure and running.
        </li>
        <li>
          <strong>A single essential cookie:</strong> an HTTP-only session cookie that keeps you signed in. We don't
          use cookies for advertising or tracking.
        </li>
        <li>
          <strong>Your browser's local storage:</strong> your email, display name, and profile photo are saved in
          your browser (not on our servers) purely so a returning sign-in screen can greet you by name. This never
          leaves your device - clearing your browser data or using a private window simply forgets it.
        </li>
      </ul>

      <h2>5. How We Use Your Information</h2>
      <p>We use the information above to:</p>
      <ul>
        <li>Create and secure your account, and keep you signed in</li>
        <li>Turn your real steps and workouts into progress on your active walks</li>
        <li>Generate the checkpoints, routes, and postcards that make up a walk</li>
        <li>Send checkpoint emails, if you've turned that on</li>
        <li>Respond to support requests you send us</li>
        <li>Keep the Service secure and working correctly</li>
      </ul>

      <h2>6. Information Sharing</h2>
      <p>
        We do not sell your personal information. We share information only with the service providers that help us
        run WorldWalker, and only as needed to provide the Service:
      </p>
      <ul>
        <li>
          <strong>Google</strong> - for "Sign in with Google" and, if you connect it, Google Health (Section 3
          above).
        </li>
        <li>
          <strong>Ollama Cloud</strong> - generates checkpoint description text from a place name and coordinates
          only.
        </li>
        <li>
          <strong>OpenStreetMap (Nominatim) and OSRM</strong> - public, open-source services we use to look up place
          names and calculate walking routes.
        </li>
        <li>
          <strong>Our hosting and database providers</strong> - who store and run the Service on our behalf.
        </li>
      </ul>
      <p>
        We may also disclose information if required by law, or if we believe it's necessary to protect the rights,
        safety, or property of WorldWalker, our users, or others.
      </p>

      <h2>7. Data Retention and Deletion</h2>
      <p>
        We keep your account and walk data for as long as your account is active. Your Google Health connection is
        kept only while it's connected (Section 3). Right now, deleting your account isn't yet a self-serve button
        in the app - email us at{' '}
        <a href="mailto:support@worldwalker.app">support@worldwalker.app</a> and we'll delete your account and all
        associated data. We're working on an in-app option for this.
      </p>

      <h2>8. Data Security</h2>
      <p>
        Passwords are stored as bcrypt hashes, never in plain text. Your Google Health tokens and any email-alert
        credentials you provide are encrypted at rest. Your sign-in session is kept in an HTTP-only, secure cookie,
        and all traffic to WorldWalker is encrypted in transit. No method of transmission or storage is perfectly
        secure, but we take reasonable, commercially appropriate measures to protect your information.
      </p>

      <h2>9. Your Rights</h2>
      <p>
        Depending on where you live, you may have the right to access, correct, delete, or export your personal
        information, or to object to or restrict how we process it. To exercise any of these rights, email{' '}
        <a href="mailto:support@worldwalker.app">support@worldwalker.app</a>. We don't sell personal information and
        don't share it for cross-context behavioral advertising, so there's no "opt out of sale" request to make.
      </p>

      <h2>10. Eligibility</h2>
      <p>
        WorldWalker is intended for users aged 18 and older. We don't knowingly collect personal information from
        anyone under 18. If we learn we've collected such information, we'll delete it promptly.
      </p>

      <h2>11. Data Breach Notification</h2>
      <p>
        If we become aware of a security breach that puts your personal information at risk, we'll investigate
        promptly and notify affected users and any applicable authority within the timeframe required by law.
      </p>

      <h2>12. Changes to This Policy</h2>
      <p>
        We may update this Privacy Policy from time to time. We'll update the "Last updated" date above, and for
        material changes, we'll do our best to let you know in-app before they take effect.
      </p>

      <h2>13. Contact Us</h2>
      <p>
        Questions about this Privacy Policy, or want to exercise one of your rights above? Email us at{' '}
        <a href="mailto:support@worldwalker.app">support@worldwalker.app</a>.
      </p>
    </LegalPage>
  )
}
