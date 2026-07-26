// E12-04/E12-05 staging smoke suite — API tier.
//
// Tier A: read-only, unauthenticated contract checks (always run).
// Tier B: read-only authenticated checks; run only when the dedicated
//         synthetic staging test account is provided via env/secrets.
//
// Rule: no test in this file directly writes persistent state. POST
// /auth/login performs the backend's existing last_login telemetry update;
// that is the sole approved side effect. The dedicated account must own and
// belong to no games so GET /games/me cannot reconcile an expired game.

import { test, expect } from '@playwright/test'
import { loadConfig, TIER_B_SKIP_REASON } from './helpers.js'

const cfg = loadConfig()

// Deterministic, syntactically valid UUID that no seeded environment uses.
const NONEXISTENT_FIELD_ID = '00000000-0000-4000-8000-000000000000'
const MY_GAMES_ARRAY_KEYS = [
  'active_games',
  'upcoming_games',
  'past_games',
  'cancelled_games',
]

async function readSensitiveJson(response, component) {
  try {
    return await response.json()
  } catch {
    throw new Error(`${component} response was not valid JSON (body suppressed)`)
  }
}

test.describe('Tier A — backend contracts', () => {
  test('[backend-health] GET / returns the health contract', async ({ request }) => {
    const response = await request.get(`${cfg.backendUrl}/`)
    expect(
      response.status(),
      '[backend-health] staging backend did not answer GET / with HTTP 200',
    ).toBe(200)

    let body
    try {
      body = await response.json()
    } catch {
      throw new Error(
        '[backend-health] GET / did not return JSON — the URL may be serving an '
        + 'infrastructure placeholder instead of the FastAPI app',
      )
    }
    expect(
      body,
      '[backend-health] GET / returned JSON but not the expected {"status":"ok"} contract',
    ).toEqual({ status: 'ok' })
  })

  test('[db-connectivity] GET /fields/ returns the public fields contract', async ({ request }) => {
    // The heaviest query in the suite: unpaginated fields plus attached game
    // payloads. Give it a larger — still bounded — budget than the default 30s.
    test.setTimeout(60_000)
    const response = await request.get(`${cfg.backendUrl}/fields/`, { timeout: 55_000 })
    expect(
      response.status(),
      '[db-connectivity] GET /fields/ did not return HTTP 200 — backend is up (see '
      + 'backend-health) but likely cannot reach its staging database',
    ).toBe(200)

    const body = await response.json()
    expect(
      Array.isArray(body),
      '[db-connectivity] GET /fields/ must return a JSON array',
    ).toBe(true)

    // An empty staging database is a valid state; only validate item shape
    // when data exists. Never assume at least one field.
    if (body.length > 0) {
      const first = body[0]
      for (const key of ['id', 'lat', 'lng', 'status', 'active_game', 'upcoming_games']) {
        expect(
          key in first,
          `[db-connectivity] field items are missing the stable "${key}" key`,
        ).toBe(true)
      }
    }
  })

  test('[api-contract] unknown field returns the 404 error envelope', async ({ request }) => {
    const response = await request.get(`${cfg.backendUrl}/fields/${NONEXISTENT_FIELD_ID}`)
    expect(
      response.status(),
      '[api-contract] GET /fields/{nonexistent} did not return HTTP 404',
    ).toBe(404)

    const body = await response.json()
    expect(body.error, '[api-contract] 404 body must set "error": true').toBe(true)
    expect(
      body.code,
      '[api-contract] 404 body must carry the stable FIELD_NOT_FOUND code',
    ).toBe('FIELD_NOT_FOUND')
    expect(
      typeof body.message,
      '[api-contract] 404 body must include a string "message"',
    ).toBe('string')
  })

  test('[cors] preflight allows the staging frontend origin', async ({ request }) => {
    const response = await request.fetch(`${cfg.backendUrl}/fields/`, {
      method: 'OPTIONS',
      headers: {
        Origin: cfg.frontendOrigin,
        'Access-Control-Request-Method': 'GET',
      },
    })
    expect(
      response.status(),
      `[cors] preflight for origin ${cfg.frontendOrigin} was rejected — staging `
      + 'CORS_ORIGINS does not include the staging frontend origin',
    ).toBe(200)

    const allowOrigin = response.headers()['access-control-allow-origin']
    expect(
      allowOrigin,
      '[cors] preflight response is missing access-control-allow-origin',
    ).toBeTruthy()
    // The backend runs CORSMiddleware with allow_credentials=True and an
    // explicit origin list (backend/app/main.py) — the allowed origin must be
    // echoed exactly, never a wildcard.
    expect(
      allowOrigin,
      '[cors] wildcard allow-origin violates the app CORS configuration '
      + '(explicit origins with credentials)',
    ).not.toBe('*')
    expect(
      allowOrigin,
      '[cors] allow-origin did not echo the staging frontend origin',
    ).toBe(cfg.frontendOrigin)
  })
})

test.describe.serial('Tier B — authenticated read-only smoke (optional)', () => {
  test.skip(!cfg.tierB.enabled, TIER_B_SKIP_REASON)

  // Populated by [auth-login] and reused by the later tests in this serial
  // group. On retry the whole group restarts, so the token is never stale.
  let accessToken = null
  let authenticatedUser = null

  test('[auth-login] staging test account can log in', async ({ request }) => {
    const response = await request.post(`${cfg.backendUrl}/auth/login`, {
      data: { username: cfg.tierB.email, password: cfg.tierB.password },
    })
    // Body and credentials are deliberately never printed on failure.
    expect(
      response.status(),
      '[auth-login] POST /auth/login did not return HTTP 200 for the staging test '
      + 'account (response body suppressed; check credential secrets and account state)',
    ).toBe(200)

    const body = await readSensitiveJson(response, '[auth-login]')
    expect(
      typeof body.access_token === 'string' && body.access_token.length > 0,
      '[auth-login] login response is missing a non-empty access_token',
    ).toBe(true)
    expect(
      body.token_type,
      '[auth-login] login response is missing the expected token_type',
    ).toBe('bearer')
    accessToken = body.access_token
    authenticatedUser = body.user
  })

  test('[auth-user-data] login response identifies the synthetic account', async () => {
    expect(
      typeof authenticatedUser?.id === 'string' && authenticatedUser.id.length > 0,
      '[auth-user-data] login response user is missing a non-empty id',
    ).toBe(true)
    expect(
      typeof authenticatedUser?.email === 'string'
        && authenticatedUser.email.trim().toLowerCase() === cfg.tierB.email.toLowerCase(),
      '[auth-user-data] login response user does not match the configured synthetic account '
      + '(email values suppressed)',
    ).toBe(true)
  })

  test('[games-me-contract] GET /games/me returns four empty game arrays', async ({ request }) => {
    expect(
      typeof accessToken === 'string' && accessToken.length > 0,
      '[games-me-contract] no token from [auth-login]',
    ).toBe(true)
    const response = await request.get(`${cfg.backendUrl}/games/me`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    })
    expect(
      response.status(),
      '[games-me-contract] GET /games/me did not return HTTP 200 with a fresh token',
    ).toBe(200)
    const body = await readSensitiveJson(response, '[games-me-contract]')
    for (const key of MY_GAMES_ARRAY_KEYS) {
      expect(
        Array.isArray(body?.[key]),
        `[games-me-contract] response must contain an array at "${key}"`,
      ).toBe(true)
      expect(
        body[key].length,
        `[games-me-contract] synthetic account "${key}" must remain empty; `
        + 'do not reuse this identity for mutable tests',
      ).toBe(0)
    }
  })

  test('[notifications-contract] GET /notifications/unread-count returns a count', async ({ request }) => {
    expect(accessToken, '[notifications-contract] no token from [auth-login]').toBeTruthy()
    const response = await request.get(`${cfg.backendUrl}/notifications/unread-count`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    })
    expect(
      response.status(),
      '[notifications-contract] GET /notifications/unread-count did not return HTTP 200',
    ).toBe(200)
    const body = await readSensitiveJson(response, '[notifications-contract]')
    expect(
      Number.isInteger(body.unread_count) && body.unread_count >= 0,
      '[notifications-contract] response must contain a non-negative integer unread_count',
    ).toBe(true)
  })

  test('[auth-rejection] invalid bearer token is rejected with 401', async ({ request }) => {
    const response = await request.get(`${cfg.backendUrl}/games/me`, {
      headers: { Authorization: 'Bearer invalid-smoke-test-token' },
    })
    expect(
      response.status(),
      '[auth-rejection] a syntactically invalid token must be rejected with HTTP 401',
    ).toBe(401)
    const body = await readSensitiveJson(response, '[auth-rejection]')
    expect(
      body.code,
      '[auth-rejection] 401 body must carry the stable AUTH_REQUIRED code',
    ).toBe('AUTH_REQUIRED')
  })

  test('[authz-boundary] non-admin token gets 403 from admin endpoints', async ({ request }) => {
    expect(accessToken, '[authz-boundary] no token from [auth-login]').toBeTruthy()
    const response = await request.get(`${cfg.backendUrl}/admin/stats`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    })
    expect(
      response.status(),
      '[authz-boundary] the non-admin staging test account must receive HTTP 403 '
      + 'from GET /admin/stats — if this returns 200 the test account has admin '
      + 'privileges, which violates the Tier B account contract',
    ).toBe(403)
    const body = await readSensitiveJson(response, '[authz-boundary]')
    expect(
      body.code,
      '[authz-boundary] 403 body must carry the stable FORBIDDEN code',
    ).toBe('FORBIDDEN')
  })
})
