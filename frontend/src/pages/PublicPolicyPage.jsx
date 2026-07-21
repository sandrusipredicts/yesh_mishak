import { useEffect } from 'react'

import './PublicPolicyPage.css'

const CONTACT_EMAIL = 'support@yesh-mishak.com'
const LAST_UPDATED = 'July 21, 2026'

const policyContent = {
  privacy: {
    eyebrow: 'Legal',
    title: 'Privacy Policy',
    introduction: (
      <p>
        This Privacy Policy explains how Yesh Mishak collects, uses, and protects information when
        you use our website and mobile application (the “Service”).
      </p>
    ),
    sections: [
      {
        title: 'Data collected',
        content: (
          <>
            <p>Depending on how you use the Service, we may collect:</p>
            <ul>
              <li>
                <strong>Account information:</strong> your name, username, email address, phone
                number, authentication details, and an internal account identifier.
              </li>
              <li>
                <strong>Profile and activity information:</strong> games you organize or join,
                fields you submit, reports you make, notification preferences, and related activity
                timestamps.
              </li>
              <li>
                <strong>Photos:</strong> images you attach to field submissions. Photo metadata
                (such as location embedded in the image) is stripped before upload.
              </li>
              <li>
                <strong>Device and technical information:</strong> session information, app
                installation identifiers, push notification tokens, device platform, anonymous
                app-usage analytics (such as which screens are visited), and limited diagnostic or
                security logs.
              </li>
              <li>
                <strong>Location information:</strong> a city you select and, only when you choose a
                location-based feature, device coordinates or a location you place on the map.
              </li>
            </ul>
          </>
        ),
      },
      {
        title: 'Google Sign-In usage',
        content: (
          <p>
            If you sign in with Google, Google provides us with an account identifier, your email
            address, name, and profile picture, when available. We use this information only to
            authenticate you, create or connect your Yesh Mishak account, and keep it secure. We do
            not use Google Sign-In to access your Google Drive, contacts, calendar, or password.
          </p>
        ),
      },
      {
        title: 'Location usage',
        content: (
          <>
            <p>
              Location access is optional and requested only when you use a feature that needs it,
              such as centering the map, finding nearby fields, choosing a field location, or setting
              a notification radius. Yesh Mishak does not track your location in the background.
            </p>
            <p>
              Your live device location is normally processed on your device and is not saved on our
              servers. Coordinates are stored when you deliberately save a location-based
              notification preference or submit a field location. Submitted field locations are
              intended to be visible to other users.
            </p>
          </>
        ),
      },
      {
        title: 'Notifications',
        content: (
          <p>
            If you enable notifications, we store your notification preferences and a device push
            token so we can send game updates, changes, and reminders. Notification content may
            include a player name, field name, or game details. Push notifications are delivered
            through services such as Firebase Cloud Messaging. You can change notification
            preferences in the Service or disable notifications in your device settings.
          </p>
        ),
      },
      {
        title: 'How we use and share information',
        content: (
          <>
            <p>
              We use information to operate and secure the Service, authenticate accounts, show
              fields and games, support participation and moderation, deliver notifications, and
              troubleshoot problems.
            </p>
            <p>
              We share information only as needed with service providers that support the Service,
              such as hosting, database, authentication, crash-reporting, map-tile, and notification
              providers, or when required by law. Some activity, including player names, game
              participation, and submitted field details, may be visible to other users as part of
              the Service.
            </p>
          </>
        ),
      },
      {
        title: 'Data retention and security',
        content: (
          <>
            <p>
              We retain information for as long as reasonably necessary to provide the Service, meet
              legal and security obligations, resolve disputes, and prevent abuse. We use reasonable
              administrative and technical safeguards, but no method of storage or transmission is
              completely secure.
            </p>
            <p>
              Anonymous usage analytics are configured for automatic deletion after 90 days. Server
              performance metrics are configured for automatic deletion after 14 days. Crash and
              diagnostic reports are retained according to our error-monitoring provider's
              project-level retention settings.
            </p>
          </>
        ),
      },
      {
        title: 'Account deletion',
        content: (
          <p>
            You can delete your Yesh Mishak account and associated personal information from the
            Settings page inside the app. You may also request deletion by emailing{' '}
            <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a> from the email address
            connected to your account. In either case, we may ask you to verify your identity. We
            will delete or de-identify account information unless we need to keep limited records for
            legal, security, fraud-prevention, or dispute-resolution purposes. Public field or game
            records may be retained in de-identified form where necessary to preserve the integrity
            of the Service.
          </p>
        ),
      },
      {
        title: 'Contact email',
        content: (
          <p>
            For privacy questions or requests, contact us at{' '}
            <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>.
          </p>
        ),
      },
    ],
  },
  terms: {
    eyebrow: 'Legal',
    title: 'Terms of Service',
    introduction: (
      <p>
        These Terms of Service govern your use of the Yesh Mishak website and mobile application
        (the “Service”). Please read them carefully.
      </p>
    ),
    sections: [
      {
        title: 'Acceptance of terms',
        content: (
          <p>
            By accessing or using the Service, you agree to these Terms and our Privacy Policy. If
            you do not agree, do not use the Service. If you use the Service on behalf of an
            organization, you represent that you have authority to bind that organization.
          </p>
        ),
      },
      {
        title: 'User responsibilities',
        content: (
          <ul>
            <li>Provide accurate account information and keep your login credentials secure.</li>
            <li>Keep game, field, and availability information you submit accurate and current.</li>
            <li>Use the Service lawfully and respect other users, venues, and local rules.</li>
            <li>
              Decide for yourself whether a game, field, organizer, or participant is suitable and
              safe before attending.
            </li>
            <li>Notify us promptly if you believe your account has been compromised.</li>
          </ul>
        ),
      },
      {
        title: 'Game organizer responsibility',
        content: (
          <p>
            A user who creates or organizes a game is solely responsible for the accuracy of the
            game details, communicating changes or cancellations, confirming that the field may be
            used, setting appropriate participation expectations, and taking reasonable steps to
            promote a safe activity. Yesh Mishak does not organize, supervise, endorse, or guarantee
            any user-created game.
          </p>
        ),
      },
      {
        title: 'Prohibited behavior',
        content: (
          <>
            <p>You may not:</p>
            <ul>
              <li>Harass, threaten, discriminate against, impersonate, or endanger another person.</li>
              <li>Post false, misleading, unlawful, abusive, or infringing content.</li>
              <li>Create fake games, manipulate participation, spam users, or misuse reports.</li>
              <li>
                Access another person’s account, probe the Service for vulnerabilities, bypass
                access controls, scrape data, or interfere with normal operation.
              </li>
              <li>Use the Service for unauthorized commercial activity or any illegal purpose.</li>
            </ul>
            <p>
              We may remove content, restrict features, suspend accounts, or terminate access when
              we reasonably believe these Terms have been violated or users may be at risk.
            </p>
          </>
        ),
      },
      {
        title: 'Disclaimer',
        content: (
          <p>
            The Service is provided on an “as is” and “as available” basis. To the fullest extent
            permitted by law, Yesh Mishak disclaims all warranties, express or implied, including
            warranties of accuracy, availability, fitness for a particular purpose, and
            non-infringement. We do not verify or guarantee every field, game, organizer,
            participant, venue condition, or user-submitted statement. Participation in sports and
            in-person activities involves inherent risks, which you voluntarily assume.
          </p>
        ),
      },
      {
        title: 'Limitation of liability',
        content: (
          <p>
            To the fullest extent permitted by law, Yesh Mishak and its operators will not be liable
            for indirect, incidental, special, consequential, or punitive damages, or for loss of
            data, profits, opportunities, or goodwill arising from the Service, user conduct,
            attendance at a game, field conditions, or inability to use the Service. Nothing in
            these Terms excludes liability that cannot legally be excluded or limited.
          </p>
        ),
      },
      {
        title: 'Changes to the Service or terms',
        content: (
          <p>
            We may update the Service or these Terms from time to time. We will post the revised
            Terms with a new “Last updated” date. Your continued use of the Service after an update
            means you accept the revised Terms. We may also suspend or discontinue all or part of
            the Service where reasonably necessary.
          </p>
        ),
      },
      {
        title: 'Contact information',
        content: (
          <p>
            Questions about these Terms may be sent to{' '}
            <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>.
          </p>
        ),
      },
    ],
  },
}

function PublicPolicyPage({ policy }) {
  const content = policyContent[policy]

  useEffect(() => {
    const previousTitle = document.title
    document.title = `${content.title} | Yesh Mishak`

    return () => {
      document.title = previousTitle
    }
  }, [content.title])

  return (
    <main className="public-policy-page" dir="ltr">
      <header className="public-policy-header">
        <a className="public-policy-brand" href="/" aria-label="Yesh Mishak home">
          yesh_mishak
        </a>
        <nav className="public-policy-nav" aria-label="Legal pages">
          <a href="/privacy" aria-current={policy === 'privacy' ? 'page' : undefined}>
            Privacy
          </a>
          <a href="/terms" aria-current={policy === 'terms' ? 'page' : undefined}>
            Terms
          </a>
        </nav>
      </header>

      <article className="public-policy-card" aria-labelledby="policy-title">
        <div className="public-policy-intro">
          <span className="public-policy-eyebrow">{content.eyebrow}</span>
          <h1 id="policy-title">{content.title}</h1>
          <p className="public-policy-updated">Last updated: {LAST_UPDATED}</p>
          {content.introduction}
        </div>

        <div className="public-policy-sections">
          {content.sections.map((section) => (
            <section key={section.title}>
              <h2>{section.title}</h2>
              {section.content}
            </section>
          ))}
        </div>
      </article>

      <footer className="public-policy-footer">
        <span>© 2026 Yesh Mishak</span>
        <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>
      </footer>
    </main>
  )
}

export default PublicPolicyPage
