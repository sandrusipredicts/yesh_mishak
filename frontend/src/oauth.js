import { App } from '@capacitor/app'
import { Browser } from '@capacitor/browser'
import { Capacitor } from '@capacitor/core'

import { loginWithSupabase, saveAuthSession } from './api/auth'
import { getSupabase } from './supabase'

const NATIVE_CALLBACK_URL = 'yeshmishak://auth-callback'
let initialized = false
let sessionBridgePromise = null

async function createInternalSession(session) {
  if (!session?.access_token) {
    throw new Error('Supabase did not return an access token')
  }

  if (!sessionBridgePromise) {
    sessionBridgePromise = loginWithSupabase(session.access_token)
      .then(saveAuthSession)
      .finally(() => {
        sessionBridgePromise = null
      })
  }

  const user = await sessionBridgePromise
  if (window.location.pathname === '/auth/callback') {
    window.history.replaceState(null, '', '/')
  }
  return user
}

function reportOAuthError(error) {
  console.error('Google OAuth login failed:', error)
  window.dispatchEvent(new CustomEvent('auth-oauth-error', { detail: error }))
}

export function initializeOAuthBridge() {
  if (initialized) return
  initialized = true

  App.addListener('appUrlOpen', async ({ url }) => {
    if (!url.startsWith(NATIVE_CALLBACK_URL)) return

    try {
      await Browser.close()
      const supabase = getSupabase()
      const code = new URL(url).searchParams.get('code')
      if (!code) throw new Error('OAuth callback did not include an authorization code')
      const { data, error } = await supabase.auth.exchangeCodeForSession(code)
      if (error) {
        console.error('Failed to exchange OAuth code for session:', error)
        reportOAuthError(error)
        return
      }
      await createInternalSession(data.session)
    } catch (error) {
      reportOAuthError(error)
    }
  })

  let supabase
  try {
    supabase = getSupabase()
  } catch {
    return
  }

  supabase.auth.onAuthStateChange((event, session) => {
    if (event === 'SIGNED_IN' && !localStorage.getItem('access_token')) {
      window.setTimeout(() => {
        createInternalSession(session).catch(reportOAuthError)
      }, 0)
    }
  })
}

export async function startGoogleOAuth() {
  const supabase = getSupabase()
  const isNative = Capacitor.isNativePlatform()
  const redirectTo = isNative
    ? NATIVE_CALLBACK_URL
    : `${window.location.origin}/auth/callback`

  const { data, error } = await supabase.auth.signInWithOAuth({
    provider: 'google',
    options: {
      redirectTo,
      skipBrowserRedirect: isNative,
    },
  })

  if (error) throw error
  if (isNative) {
    if (!data.url) throw new Error('Supabase did not return an OAuth URL')
    await Browser.open({ url: data.url })
  }
}
