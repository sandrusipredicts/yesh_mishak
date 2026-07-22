# Privacy and store-listing alignment checklist

Public URL proposed for Play Console: `https://yesh-mishak.com/privacy`

## Automated/repository evidence

- [x] A logged-out `/privacy` application route exists.
- [x] The policy identifies Yesh Mishak and lists `support@yesh-mishak.com`.
- [x] The policy covers account/profile activity, reports and blocks, Terms acceptance, optional foreground location, push notifications, service providers, retention/security, in-app deletion, and the logged-out deletion route.
- [x] Android declares foreground coarse/fine location and notification permissions; it does not declare background location.

## Manual release blockers

- [ ] Deploy the policy at the exact HTTPS URL and verify it without login, redirects to authentication, region restrictions, or certificate errors.
- [ ] Legal/privacy owner verifies that field photos/media are disclosed if enabled in the release candidate.
- [ ] Legal/privacy owner verifies first-party analytics, Sentry/crash diagnostics, installation identifiers, processors, retention periods, and international transfers are described accurately.
- [ ] Operations owner proves the deletion mailbox is monitored and the public `#account-deletion` route can be used to initiate deletion without installing or opening the app.
- [ ] Deploy and exercise the identity-verified in-app deletion flow against production for both password and Google-only accounts.
- [ ] Data safety worksheet, SDK inventory, network trace, and privacy text agree.
- [ ] Policy revision date matches the deployed page used for submission.

Do not upload a Data safety declaration or submit the app for review until every manual blocker is resolved or a named legal owner records an explicit exception.
