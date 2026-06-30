import { createClient } from '@supabase/supabase-js'

let client

export function getSupabase() {
  if (client) return client

  const supabaseUrl = import.meta.env.VITE_SUPABASE_URL
  const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY
  if (!supabaseUrl || !supabaseAnonKey) {
    throw new Error('Supabase OAuth is not configured')
  }

  client = createClient(supabaseUrl, supabaseAnonKey, {
    auth: {
      flowType: 'pkce',
      persistSession: true,
      detectSessionInUrl: true,
    },
  })
  return client
}
