# Privacy and store-listing alignment checklist

Public URL proposed for Play Console: `https://yesh-mishak.com/privacy`

## Automated/repository evidence

- [x] A logged-out `/privacy` application route exists.
- [x] The policy identifies Yesh Mishak and lists `support@yesh-mishak.com`.
- [x] The policy covers account/profile activity, optional foreground location, push notifications, service providers, retention/security, and email-based deletion requests.
- [x] Android declares foreground coarse/fine location and notification permissions; it does not declare background location.

## Manual release blockers

- [ ] Deploy the policy at the exact HTTPS URL and verify it without login, redirects to authentication, region restrictions, or certificate errors.
- [ ] Legal/privacy owner verifies that field photos/media are disclosed if enabled in the release candidate.
- [ ] Legal/privacy owner verifies first-party analytics, Sentry/crash diagnostics, installation identifiers, processors, retention periods, and international transfers are described accurately.
- [ ] Operations owner proves the deletion mailbox is monitored and a request can be identity-verified, fulfilled, and documented.
- [ ] Product/legal owner confirms whether a dedicated public account-deletion webpage is required instead of the policy section.
- [ ] Data safety worksheet, SDK inventory, network trace, and privacy text agree.
- [ ] Policy revision date matches the deployed page used for submission.

Do not upload a Data safety declaration or submit the app for review until every manual blocker is resolved or a named legal owner records an explicit exception.
