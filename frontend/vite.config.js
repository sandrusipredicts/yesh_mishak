import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { sentryVitePlugin } from '@sentry/vite-plugin'

// Sentry source-map upload (E09-01) only activates when a build-time auth
// token is present. SENTRY_AUTH_TOKEN is a CI/deployment secret -- never
// VITE_-prefixed, so it is read here (Node build context) and can never end
// up embedded in the client bundle. A local build with no token simply
// builds without attempting an upload: no failure, no behavior change.
const sentryAuthToken = process.env.SENTRY_AUTH_TOKEN

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    ...(sentryAuthToken
      ? [
          sentryVitePlugin({
            org: process.env.SENTRY_ORG,
            project: process.env.SENTRY_MOBILE_PROJECT,
            authToken: sentryAuthToken,
            release: {
              // Same release/dist the app itself reports under
              // (frontend/src/monitoring/config.js) -- one shared JS bundle
              // build serves web, the Android WebView, and the iOS
              // WKWebView, so a single upload here associates source maps
              // with events from all three.
              name: process.env.VITE_SENTRY_RELEASE,
              dist: process.env.VITE_SENTRY_DIST,
            },
            sourcemaps: {
              // Uploaded privately, then removed from the public deploy
              // output so production source maps are never publicly
              // downloadable.
              filesToDeleteAfterUpload: ['./dist/**/*.map'],
            },
            errorHandler: (err) => {
              // Visible in CI/build logs, but a source-map upload failure
              // must never break local builds. It MUST break official releases.
              if (process.env.VITE_SENTRY_ENVIRONMENT === 'production') {
                console.error('[sentry-vite-plugin] ERROR: Source map upload failed for official release:', err?.message || err)
                throw err
              }
              console.warn('[sentry-vite-plugin] source map upload failed:', err?.message || err)
            },
          }),
        ]
      : []),
  ],
  build: {
    // 'hidden': source maps are generated (so they exist to be uploaded)
    // but no //# sourceMappingURL comment is injected into the shipped JS,
    // so a browser/device never fetches one even if a .map briefly exists
    // in the output directory before the delete-after-upload step above.
    sourcemap: 'hidden',
  },
})
